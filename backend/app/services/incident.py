"""Incident lifecycle.

    DETECTED -> OPEN -> ACKNOWLEDGED -> INVESTIGATING -> CORRECTIVE_ACTION_PENDING
             -> UNDER_REVIEW -> RESOLVED -> CLOSED

Who does what (enforced by permissions in the routers + invariants here):
  operator    acknowledge, investigate, add notes, propose & implement corrective action,
              verify operational recovery            (incidents.*, corrective_actions.submit)
  supervisor  approve/reject/request revision of corrective actions, review & resolve,
              close with vaccine disposition, close false alarms    (corrective_actions.approve,
              incidents.review)
  anyone w/ incidents.escalate (or the worker) may escalate.

Every transition writes an immutable IncidentEvent and an AuditLog entry.
Nothing in this module ever changes batch status automatically — ML or rule signals only
create incidents; disposition is a recorded human decision.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.metrics import INCIDENT_TRANSITIONS, INCIDENTS_CREATED
from app.db.base import as_utc
from app.models import (Batch, CorrectiveAction, Incident, IncidentBatch, IncidentEvent, StorageUnit, User)
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, BatchStatus, CorrectiveActionStatus, IncidentStatus,
                              IncidentType, NotificationLevel, Role, ViolationSeverity)
from app.services import realtime
from app.services.audit import log_audit
from app.services.notification import notify_facility

logger = logging.getLogger(__name__)
S = IncidentStatus

ALLOWED_TRANSITIONS = {
    S.DETECTED: {S.OPEN, S.CLOSED},
    S.OPEN: {S.ACKNOWLEDGED, S.CLOSED},
    S.ACKNOWLEDGED: {S.INVESTIGATING, S.CLOSED},
    S.INVESTIGATING: {S.CORRECTIVE_ACTION_PENDING, S.CLOSED},
    S.CORRECTIVE_ACTION_PENDING: {S.INVESTIGATING, S.UNDER_REVIEW},
    S.UNDER_REVIEW: {S.RESOLVED, S.INVESTIGATING},
    S.RESOLVED: {S.CLOSED},
    S.CLOSED: set(),
}
_SEVERITY_RANK = {ViolationSeverity.WARNING: 1, ViolationSeverity.HIGH: 2, ViolationSeverity.CRITICAL: 3}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bad(msg: str, code: int = 400):
    raise HTTPException(status_code=code, detail=msg)


def next_incident_number(db: Session) -> str:
    year = _now().year
    prefix = f"INC-{year}-"
    last = (db.query(func.max(Incident.incident_number))
            .filter(Incident.incident_number.like(f"{prefix}%")).scalar())
    seq = 1
    if last:
        try:
            seq = int(last.rsplit("-", 1)[1]) + 1
        except ValueError:
            seq = db.query(func.count(Incident.id)).scalar() + 1
    return f"{prefix}{seq:05d}"


class IncidentService:
    ALLOWED_TRANSITIONS = ALLOWED_TRANSITIONS

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def get(db: Session, incident_id: uuid.UUID) -> Incident:
        inc = db.get(Incident, incident_id)
        if not inc:
            _bad("Incident not found", 404)
        return inc

    @staticmethod
    def _event(db: Session, inc: Incident, event_type: str, actor: Optional[User], note: Optional[str] = None,
               from_status=None, to_status=None, data: Optional[dict] = None) -> IncidentEvent:
        ev = IncidentEvent(
            incident_id=inc.id, event_type=event_type,
            from_status=from_status.value if hasattr(from_status, "value") else from_status,
            to_status=to_status.value if hasattr(to_status, "value") else to_status,
            actor_id=actor.id if actor else None, actor_name=actor.name if actor else "system",
            note=note, data=data,
        )
        db.add(ev)
        return ev

    @classmethod
    def _transition(cls, db: Session, inc: Incident, to: IncidentStatus, actor: Optional[User], event_type: str,
                    note: Optional[str] = None, data: Optional[dict] = None):
        frm = inc.status
        if to not in ALLOWED_TRANSITIONS.get(frm, set()):
            _bad(f"Invalid state transition from {frm.value} to {to.value}")
        inc.status = to
        cls._event(db, inc, event_type, actor, note, frm, to, data)
        INCIDENT_TRANSITIONS.labels(to_status=to.value).inc()
        if actor is not None:
            log_audit(db, actor, event_type, "Incident", inc.id,
                      {"incident_number": inc.incident_number, "from": frm.value, "to": to.value, "note": note},
                      facility_id=inc.facility_id, commit=False)

    @staticmethod
    def _append_note(inc: Incident, actor: User, note: Optional[str]):
        if note:
            line = f"[{_now().strftime('%Y-%m-%d %H:%M')} UTC] {actor.name}: {note}"
            inc.investigation_notes = f"{inc.investigation_notes}\n{line}" if inc.investigation_notes else line

    @staticmethod
    def _publish(inc: Incident, kind: str = "incident.updated"):
        realtime.publish(kind, {
            "id": inc.id, "incident_number": inc.incident_number, "status": inc.status, "severity": inc.severity,
            "incident_type": inc.incident_type, "title": inc.title, "storage_unit_id": inc.storage_unit_id,
        }, facility_id=inc.facility_id)

    @staticmethod
    def _require_active(inc: Incident):
        if inc.status not in ACTIVE_INCIDENT_STATUSES:
            _bad(f"Incident is {inc.status.value}; no further operational changes allowed")

    # ------------------------------------------------------------------ creation
    @classmethod
    def open_incident(cls, db: Session, *, incident_type: IncidentType, severity: ViolationSeverity,
                      facility_id: Optional[uuid.UUID], storage_unit_id: Optional[uuid.UUID] = None,
                      sensor_id: Optional[uuid.UUID] = None, title: str, description: str = "",
                      source: str = "RULE", dedup_key: Optional[str] = None, violation_id: Optional[uuid.UUID] = None,
                      is_simulated: bool = False, data: Optional[dict] = None,
                      actor: Optional[User] = None, detected_at: Optional[datetime] = None) -> Tuple[Incident, bool]:
        """Create an incident, or fold the signal into an existing active incident with the
        same dedup key. Returns (incident, created)."""
        if dedup_key:
            existing = (db.query(Incident)
                        .filter(Incident.dedup_key == dedup_key, Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
                        .order_by(Incident.created_at.desc()).first())
            if existing:
                cls._event(db, existing, "REPEATED_SIGNAL", None, description or title, data=data)
                if _SEVERITY_RANK[severity] > _SEVERITY_RANK[existing.severity]:
                    cls.raise_severity(db, existing, severity, "Repeated signal at higher severity", commit=False)
                db.commit()
                return existing, False

        inc = Incident(
            incident_number=next_incident_number(db), incident_type=incident_type, severity=severity,
            status=S.DETECTED, title=title, description=description, source=source,
            facility_id=facility_id, storage_unit_id=storage_unit_id, sensor_id=sensor_id,
            dedup_key=dedup_key, violation_id=violation_id, is_simulated=is_simulated,
            # detection time = time of the triggering reading (delayed/back-filled telemetry keeps its true time)
            created_at=min(as_utc(detected_at), _now()) if detected_at else _now(),
        )
        db.add(inc)
        db.flush()
        cls._event(db, inc, "DETECTED", actor, description or title, None, S.DETECTED, data)
        if incident_type == IncidentType.TEMPERATURE_EXCURSION:
            cls.link_affected_batches(db, inc, commit=False)
        # DETECTED -> OPEN once responsible people have been notified
        level = NotificationLevel.CRITICAL if severity == ViolationSeverity.CRITICAL else NotificationLevel.WARNING
        roles = [Role.OPERATOR, Role.SUPERVISOR] if severity == ViolationSeverity.CRITICAL else [Role.OPERATOR]
        if incident_type in (IncidentType.SENSOR_OFFLINE, IncidentType.SENSOR_FAULT, IncidentType.EQUIPMENT_FAILURE):
            roles = roles + [Role.TECHNICIAN]
        notified = notify_facility(
            db, facility_id, roles, f"{inc.incident_number}: {title}", description or title, level=level,
            category="INCIDENT", link=f"/incidents/{inc.id}", entity_type="Incident", entity_id=inc.id, commit=False)
        cls._transition(db, inc, S.OPEN, None, "OPENED", f"{len(notified)} responsible user(s) notified")
        INCIDENTS_CREATED.labels(type=incident_type.value, severity=severity.value).inc()
        db.commit()
        try:
            from app.services.alert import AlertService
            AlertService.trigger_alerts_for_incident(db, inc)
        except Exception as exc:  # alert channel failures never block incident creation
            logger.warning("Alert dispatch failed for %s: %s", inc.incident_number, exc)
        cls._publish(inc, "incident.created")
        logger.info("Incident %s opened (%s/%s)", inc.incident_number, incident_type.value, severity.value)
        return inc, True

    @classmethod
    def raise_severity(cls, db: Session, inc: Incident, severity: ViolationSeverity, reason: str, commit=True):
        if _SEVERITY_RANK[severity] <= _SEVERITY_RANK[inc.severity]:
            return
        old = inc.severity
        inc.severity = severity
        cls._event(db, inc, "SEVERITY_RAISED", None, reason, data={"from": old.value, "to": severity.value})
        if severity == ViolationSeverity.CRITICAL:
            notify_facility(db, inc.facility_id, [Role.OPERATOR, Role.SUPERVISOR],
                            f"{inc.incident_number} is now CRITICAL", reason, level=NotificationLevel.CRITICAL,
                            category="INCIDENT", link=f"/incidents/{inc.id}", entity_type="Incident",
                            entity_id=inc.id, commit=False)
        if commit:
            db.commit()
        cls._publish(inc)

    @classmethod
    def record_system_event(cls, db: Session, inc: Incident, event_type: str, note: str, data=None, commit=True):
        cls._event(db, inc, event_type, None, note, data=data)
        if commit:
            db.commit()
        cls._publish(inc)

    # ------------------------------------------------------------------ operator actions
    @classmethod
    def acknowledge(cls, db: Session, incident_id, user: User, action) -> Incident:
        inc = cls.get(db, incident_id)
        if inc.status == S.DETECTED:
            cls._transition(db, inc, S.OPEN, None, "OPENED")
        cls._transition(db, inc, S.ACKNOWLEDGED, user, "ACKNOWLEDGED", getattr(action, "notes", None))
        inc.acknowledged_at = _now()
        if inc.assigned_to is None:
            inc.assigned_to = user.id
        cls._append_note(inc, user, getattr(action, "notes", None))
        db.commit()
        cls._publish(inc)
        return inc

    @classmethod
    def investigate(cls, db: Session, incident_id, user: User, action) -> Incident:
        inc = cls.get(db, incident_id)
        cls._transition(db, inc, S.INVESTIGATING, user, "INVESTIGATION_STARTED", getattr(action, "notes", None))
        cls._append_note(inc, user, getattr(action, "notes", None))
        db.commit()
        cls._publish(inc)
        return inc

    @classmethod
    def add_note(cls, db: Session, incident_id, user: User, note: str) -> Incident:
        inc = cls.get(db, incident_id)
        cls._require_active(inc)
        if not note or not note.strip():
            _bad("Note text is required")
        cls._append_note(inc, user, note.strip())
        cls._event(db, inc, "NOTE_ADDED", user, note.strip())
        log_audit(db, user, "INCIDENT_NOTE", "Incident", inc.id, {"note": note[:500]},
                  facility_id=inc.facility_id, commit=False)
        db.commit()
        cls._publish(inc)
        return inc

    @classmethod
    def escalate(cls, db: Session, incident_id, user: Optional[User], reason: str, rule: str = "MANUAL") -> Incident:
        inc = cls.get(db, incident_id)
        cls._require_active(inc)
        inc.escalation_level += 1
        inc.escalated_at = _now()
        inc.escalation_reason = reason
        cls._event(db, inc, "ESCALATED", user, reason, data={"level": inc.escalation_level, "rule": rule})
        if user:
            log_audit(db, user, "INCIDENT_ESCALATED", "Incident", inc.id, {"reason": reason, "rule": rule},
                      facility_id=inc.facility_id, commit=False)
        notify_facility(db, inc.facility_id, [Role.SUPERVISOR],
                        f"Escalation L{inc.escalation_level}: {inc.incident_number}", reason,
                        level=NotificationLevel.CRITICAL, category="ESCALATION", link=f"/incidents/{inc.id}",
                        entity_type="Incident", entity_id=inc.id, commit=False)
        db.commit()
        from app.core.metrics import ESCALATIONS
        ESCALATIONS.labels(rule=rule).inc()
        cls._publish(inc)
        return inc

    @classmethod
    def propose_corrective_action(cls, db: Session, incident_id, user: User, *, description: str,
                                  root_cause: Optional[str], action_type: str = "OPERATIONAL",
                                  due_date: Optional[datetime] = None) -> CorrectiveAction:
        inc = cls.get(db, incident_id)
        if inc.status != S.INVESTIGATING:
            _bad("Corrective actions can only be proposed while the incident is INVESTIGATING")
        if not description or len(description.strip()) < 5:
            _bad("A corrective action description is required")
        ca = CorrectiveAction(incident_id=inc.id, description=description.strip(), root_cause=root_cause,
                              action_type=action_type, proposed_by=user.id,
                              due_date=due_date or (_now() + timedelta(days=2)))
        db.add(ca)
        db.flush()
        if root_cause:
            inc.root_cause = root_cause
        inc.corrective_action = description.strip()
        cls._transition(db, inc, S.CORRECTIVE_ACTION_PENDING, user, "CORRECTIVE_ACTION_PROPOSED", description,
                        data={"corrective_action_id": str(ca.id), "root_cause": root_cause})
        notify_facility(db, inc.facility_id, [Role.SUPERVISOR], f"Approval needed: {inc.incident_number}",
                        f"{user.name} proposed: {description[:140]}", level=NotificationLevel.WARNING,
                        category="APPROVAL", link=f"/incidents/{inc.id}", entity_type="Incident",
                        entity_id=inc.id, commit=False)
        db.commit()
        cls._publish(inc)
        return ca

    @classmethod
    def _get_ca(cls, db: Session, inc: Incident, ca_id) -> CorrectiveAction:
        ca = db.get(CorrectiveAction, ca_id)
        if not ca or ca.incident_id != inc.id:
            _bad("Corrective action not found", 404)
        return ca

    @classmethod
    def review_corrective_action(cls, db: Session, incident_id, ca_id, user: User, decision: str,
                                 comment: Optional[str]) -> CorrectiveAction:
        inc = cls.get(db, incident_id)
        ca = cls._get_ca(db, inc, ca_id)
        if ca.status != CorrectiveActionStatus.PROPOSED:
            _bad(f"Corrective action is {ca.status.value}; only PROPOSED actions can be reviewed")
        if ca.proposed_by == user.id:
            _bad("Separation of duties: you cannot review your own proposal", 403)
        decision = decision.lower()
        ca.reviewed_by, ca.reviewed_at, ca.review_comment = user.id, _now(), comment
        if decision == "approve":
            ca.status = CorrectiveActionStatus.APPROVED
            cls._event(db, inc, "CORRECTIVE_ACTION_APPROVED", user, comment, data={"corrective_action_id": str(ca.id)})
            log_audit(db, user, "CORRECTIVE_ACTION_APPROVED", "CorrectiveAction", ca.id,
                      {"incident": inc.incident_number, "comment": comment}, facility_id=inc.facility_id, commit=False)
            msg = "Corrective action approved — implement and verify recovery"
        elif decision in ("reject", "request_revision"):
            if not comment:
                _bad("A comment is required when rejecting or requesting revision")
            ca.status = (CorrectiveActionStatus.REJECTED if decision == "reject"
                         else CorrectiveActionStatus.REVISION_REQUESTED)
            cls._transition(db, inc, S.INVESTIGATING, user,
                            "CORRECTIVE_ACTION_REJECTED" if decision == "reject" else "FURTHER_INVESTIGATION_REQUESTED",
                            comment, data={"corrective_action_id": str(ca.id)})
            msg = f"Supervisor {decision.replace('_', ' ')}: {comment}"
        else:
            _bad("decision must be approve | reject | request_revision")
        notify_facility(db, inc.facility_id, [Role.OPERATOR], f"{inc.incident_number}: review decision", msg,
                        category="APPROVAL", link=f"/incidents/{inc.id}", entity_type="Incident",
                        entity_id=inc.id, commit=False)
        db.commit()
        cls._publish(inc)
        return ca

    @classmethod
    def implement_corrective_action(cls, db: Session, incident_id, ca_id, user: User, notes: Optional[str],
                                    maintenance_ticket_id: Optional[uuid.UUID] = None) -> CorrectiveAction:
        inc = cls.get(db, incident_id)
        ca = cls._get_ca(db, inc, ca_id)
        if ca.status != CorrectiveActionStatus.APPROVED:
            _bad("Only APPROVED corrective actions can be marked implemented")
        ca.status = CorrectiveActionStatus.IMPLEMENTED
        ca.implemented_at = _now()
        ca.implementation_notes = notes
        ca.maintenance_ticket_id = maintenance_ticket_id
        cls._event(db, inc, "CORRECTIVE_ACTION_IMPLEMENTED", user, notes, data={"corrective_action_id": str(ca.id)})
        log_audit(db, user, "CORRECTIVE_ACTION_IMPLEMENTED", "CorrectiveAction", ca.id, {"notes": notes},
                  facility_id=inc.facility_id, commit=False)
        db.commit()
        cls._publish(inc)
        return ca

    @classmethod
    def verify_recovery(cls, db: Session, incident_id, user: User, notes: Optional[str]) -> Incident:
        inc = cls.get(db, incident_id)
        if inc.status != S.CORRECTIVE_ACTION_PENDING:
            _bad("Recovery can only be verified once a corrective action has been approved and implemented")
        cas = inc.corrective_actions
        if any(c.status == CorrectiveActionStatus.PROPOSED for c in cas):
            _bad("A corrective action is still awaiting supervisor review")
        implemented = [c for c in cas if c.status == CorrectiveActionStatus.IMPLEMENTED]
        if not implemented:
            _bad("At least one approved corrective action must be implemented first")
        if inc.violation is not None and inc.violation.status.value == "OPEN":
            _bad("Temperature is still outside approved limits — recovery cannot be verified yet")
        for c in implemented:
            c.status = CorrectiveActionStatus.VERIFIED
        inc.recovery_verified_at = _now()
        cls._append_note(inc, user, notes)
        cls._transition(db, inc, S.UNDER_REVIEW, user, "RECOVERY_VERIFIED", notes)
        notify_facility(db, inc.facility_id, [Role.SUPERVISOR], f"Review required: {inc.incident_number}",
                        "Operational recovery verified; awaiting supervisor review", level=NotificationLevel.WARNING,
                        category="APPROVAL", link=f"/incidents/{inc.id}", entity_type="Incident",
                        entity_id=inc.id, commit=False)
        if inc.incident_type == IncidentType.TEMPERATURE_EXCURSION:
            cls.link_affected_batches(db, inc, commit=False)
        db.commit()
        cls._publish(inc)
        return inc

    # ------------------------------------------------------------------ supervisor actions
    @classmethod
    def review(cls, db: Session, incident_id, user: User, decision: str, notes: Optional[str]) -> Incident:
        inc = cls.get(db, incident_id)
        if inc.status != S.UNDER_REVIEW:
            _bad("Incident is not awaiting review")
        decision = decision.lower()
        if decision == "resolve":
            inc.review_decision, inc.reviewed_by, inc.reviewed_at, inc.review_notes = "RESOLVED", user.id, _now(), notes
            inc.resolved_at = _now()
            cls._transition(db, inc, S.RESOLVED, user, "RESOLVED", notes)
        elif decision == "request_more_investigation":
            if not notes:
                _bad("Notes are required when requesting further investigation")
            inc.review_decision = "MORE_INVESTIGATION"
            cls._transition(db, inc, S.INVESTIGATING, user, "FURTHER_INVESTIGATION_REQUESTED", notes)
            notify_facility(db, inc.facility_id, [Role.OPERATOR], f"{inc.incident_number}: more investigation requested",
                            notes, category="APPROVAL", link=f"/incidents/{inc.id}", entity_type="Incident",
                            entity_id=inc.id, commit=False)
        else:
            _bad("decision must be resolve | request_more_investigation")
        db.commit()
        cls._publish(inc)
        return inc

    @classmethod
    def close(cls, db: Session, incident_id, user: User, action) -> Incident:
        inc = cls.get(db, incident_id)
        evidence = getattr(action, "closure_evidence", None) or getattr(action, "notes", None)
        disposition = getattr(action, "vaccine_disposition", None)
        false_alarm = bool(getattr(action, "false_alarm", False))
        if inc.status == S.RESOLVED:
            affected = db.query(IncidentBatch).filter(IncidentBatch.incident_id == inc.id).count()
            if affected and not disposition:
                _bad("Vaccine disposition must be recorded for the potentially affected batches before closure")
            event = "CLOSED"
        elif inc.status in ACTIVE_INCIDENT_STATUSES and false_alarm:
            if not evidence:
                _bad("A justification is required to close an incident as a false alarm")
            inc.review_decision, inc.reviewed_by, inc.reviewed_at = "FALSE_ALARM", user.id, _now()
            event = "CLOSED_FALSE_ALARM"
        else:
            _bad("Only RESOLVED incidents can be closed (or active incidents explicitly marked as false alarm)")
        inc.closure_evidence = evidence
        if disposition:
            inc.vaccine_disposition = disposition
            inc.disposition_by = user.id
        inc.closed_at = _now()
        cls._transition(db, inc, S.CLOSED, user, event, evidence,
                        data={"vaccine_disposition": disposition} if disposition else None)
        db.commit()
        cls._publish(inc)
        return inc

    @classmethod
    def assign(cls, db: Session, incident_id, user: User, action) -> Incident:
        from app.services.access import resolve_scope
        inc = cls.get(db, incident_id)
        assignee_id = getattr(action, "assignee_id", None)
        if not assignee_id:
            _bad("Assignee ID is required")
        assignee = db.get(User, assignee_id)
        if not assignee or not assignee.is_active or assignee.role != Role.OPERATOR:
            _bad("Assignee must be an active facility operator")
        if not resolve_scope(db, assignee).can_access_facility(inc.facility_id):
            _bad("Assignee is not assigned to this incident's facility")
        inc.assigned_to = assignee.id
        cls._event(db, inc, "ASSIGNED", user, f"Assigned to {assignee.name}", data={"assignee_id": str(assignee.id)})
        log_audit(db, user, "INCIDENT_ASSIGNED", "Incident", inc.id, {"assignee": str(assignee.id)},
                  facility_id=inc.facility_id, commit=False)
        db.commit()
        cls._publish(inc)
        return inc

    # ------------------------------------------------------------------ batches (preserved v1 logic)
    @classmethod
    def _overlapping_batches(cls, db: Session, inc: Incident):
        v = inc.violation
        if not v:
            return [], None, None
        start = v.start_time
        end = v.end_time or _now()
        batches = db.query(Batch).filter(
            Batch.storage_unit_id == v.storage_unit_id,
            Batch.start_time <= end,
            (Batch.end_time.is_(None)) | (Batch.end_time >= start),
        ).all()
        return batches, start, v.end_time

    @classmethod
    def link_affected_batches(cls, db: Session, inc: Incident, commit: bool = True):
        batches, _, _ = cls._overlapping_batches(db, inc)
        existing = {a.batch_id for a in db.query(IncidentBatch).filter(IncidentBatch.incident_id == inc.id)}
        for b in batches:
            if b.id not in existing:
                db.add(IncidentBatch(incident_id=inc.id, batch_id=b.id))
        if commit:
            db.commit()
        return batches

    @classmethod
    def identify_affected_batches(cls, db: Session, incident_id) -> list[dict]:
        """Read-only: batches present in the unit during the excursion window."""
        inc = cls.get(db, incident_id)
        batches, start, end = cls._overlapping_batches(db, inc)
        linked = {a.batch_id for a in db.query(IncidentBatch).filter(IncidentBatch.incident_id == inc.id)}
        ids = {b.id for b in batches} | linked
        rows = db.query(Batch).filter(Batch.id.in_(ids)).all() if ids else []
        return [{
            "batch_id": b.id, "batch_number": b.batch_number, "product_name": b.product.name,
            "storage_unit_code": b.storage_unit.unit_code, "status": b.status.value,
            "current_quantity": b.current_quantity, "expiry_date": b.expiry_date,
            "excursion_start": start or inc.created_at, "excursion_end": end,
            "message": "POTENTIALLY AFFECTED BATCH — disposition requires authorised review",
        } for b in rows]

    @staticmethod
    def duration_seconds(inc: Incident) -> int:
        end = as_utc(inc.closed_at or inc.resolved_at) or _now()
        return int((end - as_utc(inc.created_at)).total_seconds())


def active_quarantine_candidates(db: Session, inc: Incident):
    return [a.batch for a in inc.batch_associations if a.batch.status == BatchStatus.ACTIVE]


def unit_for(db: Session, inc: Incident) -> Optional[StorageUnit]:
    return db.get(StorageUnit, inc.storage_unit_id) if inc.storage_unit_id else None
