import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import get_db, require_permission
from app.models import Incident, IncidentBatch, StorageUnit, TemperatureReading
from app.models.enums import ACTIVE_INCIDENT_STATUSES, IncidentStatus, IncidentType, ViolationSeverity
from app.schemas.common import Page, paginate
from app.schemas.incident import (AffectedBatchResponse, CorrectiveActionImplement, CorrectiveActionIn,
                                  CorrectiveActionOut, CorrectiveActionReview, EscalateRequest, IncidentActionRequest,
                                  IncidentDetail, IncidentEventOut, IncidentResponse, ManualIncidentIn, NoteRequest,
                                  ReviewRequest, VerifyRecoveryRequest)
from app.services.access import AccessScope
from app.services.incident import IncidentService

router = APIRouter()


def _load(db: Session, incident_id: uuid.UUID, scope: AccessScope) -> Incident:
    inc = db.get(Incident, incident_id)
    if not inc:
        raise HTTPException(404, "Incident not found")
    scope.ensure(inc.facility_id, not_found="Incident not found")
    return inc


def _detail(db: Session, inc: Incident, scope: AccessScope) -> dict:
    db.refresh(inc)
    d = ser.incident(inc)
    d["events"] = [IncidentEventOut.model_validate(e).model_dump() for e in inc.events]
    d["corrective_actions"] = [ser.corrective_action(c) for c in inc.corrective_actions]
    d["affected_batch_count"] = db.query(IncidentBatch).filter(IncidentBatch.incident_id == inc.id).count()
    d["available_actions"] = ser.available_incident_actions(inc, scope)
    return d


@router.get("", response_model=Page[IncidentResponse])
def list_incidents(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                   status: Optional[List[IncidentStatus]] = Query(None), active: Optional[bool] = None,
                   severity: Optional[ViolationSeverity] = None, incident_type: Optional[IncidentType] = None,
                   facility_id: Optional[uuid.UUID] = None, storage_unit_id: Optional[uuid.UUID] = None,
                   assigned_to: Optional[uuid.UUID] = None, escalated: Optional[bool] = None,
                   search: Optional[str] = Query(None, max_length=100), days: Optional[int] = Query(None, ge=1, le=3650),
                   simulated: Optional[bool] = None, sort: str = Query("-created_at", pattern="^-?(created_at|severity|status)$"),
                   db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("incidents.view"))) -> Any:
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(Incident), Incident.facility_id)
    if status:
        q = q.filter(Incident.status.in_(status))
    if active is True:
        q = q.filter(Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
    elif active is False:
        q = q.filter(Incident.status.notin_(ACTIVE_INCIDENT_STATUSES))
    if severity:
        q = q.filter(Incident.severity == severity)
    if incident_type:
        q = q.filter(Incident.incident_type == incident_type)
    if facility_id:
        q = q.filter(Incident.facility_id == facility_id)
    if storage_unit_id:
        q = q.filter(Incident.storage_unit_id == storage_unit_id)
    if assigned_to:
        q = q.filter(Incident.assigned_to == assigned_to)
    if escalated:
        q = q.filter(Incident.escalation_level > 0)
    if simulated is not None:
        q = q.filter(Incident.is_simulated.is_(simulated))
    if days:
        q = q.filter(Incident.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(Incident.incident_number.ilike(like), Incident.title.ilike(like)))
    col = getattr(Incident, sort.lstrip("-"))
    q = q.order_by(col.desc() if sort.startswith("-") else col.asc())
    items, total = paginate(q, page, page_size)
    return {"items": [ser.incident(i) for i in items], "total": total, "page": page, "page_size": page_size}


@router.post("", response_model=IncidentDetail, status_code=201)
def report_incident(body: ManualIncidentIn, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("incidents.investigate"))):
    """Operator-reported incident (e.g. equipment failure observed on site)."""
    unit = db.get(StorageUnit, body.storage_unit_id)
    if not unit:
        raise HTTPException(404, "Storage unit not found")
    scope.ensure(unit.facility_id, not_found="Storage unit not found")
    inc, _ = IncidentService.open_incident(
        db, incident_type=body.incident_type, severity=body.severity, facility_id=unit.facility_id,
        storage_unit_id=unit.id, title=body.title, description=body.description, source="MANUAL", actor=scope.user)
    return _detail(db, inc, scope)


@router.get("/{incident_id}", response_model=IncidentDetail)
def get_incident(incident_id: uuid.UUID, db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("incidents.view"))):
    return _detail(db, _load(db, incident_id, scope), scope)


@router.get("/{incident_id}/events", response_model=List[IncidentEventOut])
def incident_events(incident_id: uuid.UUID, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("incidents.view"))):
    return _load(db, incident_id, scope).events


@router.get("/{incident_id}/evidence")
def incident_evidence(incident_id: uuid.UUID, padding_minutes: int = Query(60, ge=0, le=24 * 60),
                      db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("incidents.view"))):
    """Temperature readings around the incident window (immutable evidence for review)."""
    inc = _load(db, incident_id, scope)
    if not inc.storage_unit_id:
        return {"points": []}
    start = (inc.excursion_start or inc.created_at)
    end = inc.excursion_end or inc.resolved_at or datetime.now(timezone.utc)
    pad = timedelta(minutes=padding_minutes)
    rows = (db.query(TemperatureReading).filter(TemperatureReading.storage_unit_id == inc.storage_unit_id,
                                                TemperatureReading.timestamp >= start - pad,
                                                TemperatureReading.timestamp <= end + pad)
            .order_by(TemperatureReading.timestamp).limit(5000).all())
    unit = inc.storage_unit
    return {"window_start": start, "window_end": inc.excursion_end, "min_limit": unit.effective_min,
            "max_limit": unit.effective_max, "peak": inc.peak_temperature,
            "points": [{"t": r.timestamp, "v": r.temperature, "q": r.quality_status, "sim": r.is_simulated,
                        "anomaly": r.anomaly.detection_method if r.anomaly else None} for r in rows]}


@router.post("/{incident_id}/acknowledge", response_model=IncidentDetail)
def acknowledge(incident_id: uuid.UUID, body: IncidentActionRequest, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("incidents.acknowledge"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.acknowledge(db, incident_id, scope.user, body), scope)


@router.post("/{incident_id}/investigate", response_model=IncidentDetail)
def investigate(incident_id: uuid.UUID, body: IncidentActionRequest, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("incidents.investigate"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.investigate(db, incident_id, scope.user, body), scope)


@router.post("/{incident_id}/notes", response_model=IncidentDetail)
def add_note(incident_id: uuid.UUID, body: NoteRequest, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("incidents.investigate"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.add_note(db, incident_id, scope.user, body.note), scope)


@router.post("/{incident_id}/escalate", response_model=IncidentDetail)
def escalate(incident_id: uuid.UUID, body: EscalateRequest, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("incidents.escalate"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.escalate(db, incident_id, scope.user, body.reason), scope)


@router.post("/{incident_id}/corrective-actions", response_model=CorrectiveActionOut, status_code=201)
def propose_ca(incident_id: uuid.UUID, body: CorrectiveActionIn, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("corrective_actions.submit"))):
    _load(db, incident_id, scope)
    ca = IncidentService.propose_corrective_action(db, incident_id, scope.user, description=body.description,
                                                   root_cause=body.root_cause, action_type=body.action_type,
                                                   due_date=body.due_date)
    return ser.corrective_action(ca)


@router.post("/{incident_id}/corrective-actions/{ca_id}/review", response_model=CorrectiveActionOut)
def review_ca(incident_id: uuid.UUID, ca_id: uuid.UUID, body: CorrectiveActionReview, db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("corrective_actions.approve"))):
    _load(db, incident_id, scope)
    return ser.corrective_action(IncidentService.review_corrective_action(db, incident_id, ca_id, scope.user,
                                                                          body.decision, body.comment))


@router.post("/{incident_id}/corrective-actions/{ca_id}/implement", response_model=CorrectiveActionOut)
def implement_ca(incident_id: uuid.UUID, ca_id: uuid.UUID, body: CorrectiveActionImplement,
                 db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("corrective_actions.submit"))):
    _load(db, incident_id, scope)
    return ser.corrective_action(IncidentService.implement_corrective_action(
        db, incident_id, ca_id, scope.user, body.notes, body.maintenance_ticket_id))


@router.post("/{incident_id}/verify-recovery", response_model=IncidentDetail)
def verify_recovery(incident_id: uuid.UUID, body: VerifyRecoveryRequest, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("corrective_actions.submit"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.verify_recovery(db, incident_id, scope.user, body.notes), scope)


@router.post("/{incident_id}/review", response_model=IncidentDetail)
def review(incident_id: uuid.UUID, body: ReviewRequest, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("incidents.review"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.review(db, incident_id, scope.user, body.decision, body.notes), scope)


@router.post("/{incident_id}/close", response_model=IncidentDetail)
def close(incident_id: uuid.UUID, body: IncidentActionRequest, db: Session = Depends(get_db),
          scope: AccessScope = Depends(require_permission("incidents.review"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.close(db, incident_id, scope.user, body), scope)


@router.post("/{incident_id}/assign", response_model=IncidentDetail)
def assign(incident_id: uuid.UUID, body: IncidentActionRequest, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("incidents.assign"))):
    _load(db, incident_id, scope)
    return _detail(db, IncidentService.assign(db, incident_id, scope.user, body), scope)


@router.get("/{incident_id}/affected-batches", response_model=List[AffectedBatchResponse])
def affected_batches(incident_id: uuid.UUID, db: Session = Depends(get_db),
                     scope: AccessScope = Depends(require_permission("incidents.view", "inventory.view"))):
    _load(db, incident_id, scope)
    return IncidentService.identify_affected_batches(db, incident_id)


@router.post("/{incident_id}/ai-summary")
def ai_summary(incident_id: uuid.UUID, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("incidents.investigate"))):
    """Preserved v1 assistant (mock provider, labelled as AI-generated, no safety decisions)."""
    _load(db, incident_id, scope)
    from app.services.ai_assistant import AIAssistantService
    return {"ai_summary": AIAssistantService.generate_summary(db, incident_id)}
