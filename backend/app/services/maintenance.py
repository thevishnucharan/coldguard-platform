"""Maintenance tickets, calibration and equipment history.

Ticket workflow:  OPEN -> ASSIGNED -> IN_PROGRESS -> RESOLVED -> VERIFIED -> CLOSED

Automatic tickets are labelled by trigger:
  RULE  deterministic conditions (offline incident, low battery, calibration due, repeated
        excursions, repeated failures). These are rule-based, NOT predictive.
  ML    unit with sustained anomaly clusters (model-based signal; decision support).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.metrics import MAINT_TICKETS
from app.db.base import as_utc
from app.models import (Anomaly, Batch, CalibrationRecord, EquipmentEvent, Incident, MaintenanceNote,
                        MaintenanceTicket, Sensor, StorageUnit, User)
from app.models.enums import (ACTIVE_MAINTENANCE_STATUSES, CalibrationResult, IncidentType, MaintenancePriority,
                              MaintenanceStatus, MaintenanceTrigger, MaintenanceType, MovementType, NotificationLevel,
                              Role, SensorStatus, StorageUnitStatus)
from app.services import realtime
from app.services.audit import log_audit
from app.services.notification import notify, notify_facility

M = MaintenanceStatus
TRANSITIONS = {
    M.OPEN: {M.ASSIGNED},
    M.ASSIGNED: {M.IN_PROGRESS, M.ASSIGNED},
    M.IN_PROGRESS: {M.RESOLVED},
    M.RESOLVED: {M.VERIFIED, M.IN_PROGRESS},
    M.VERIFIED: {M.CLOSED},
    M.CLOSED: set(),
}


def _now():
    return datetime.now(timezone.utc)


def _bad(msg, code=400):
    raise HTTPException(status_code=code, detail=msg)


def next_ticket_number(db: Session) -> str:
    prefix = f"WO-{_now().year}-"
    last = db.query(func.max(MaintenanceTicket.ticket_number)).filter(
        MaintenanceTicket.ticket_number.like(f"{prefix}%")).scalar()
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:05d}"


def equipment_event(db: Session, entity_type: str, entity_id, event_type: str, details: dict,
                    actor: Optional[User], facility_id=None):
    db.add(EquipmentEvent(entity_type=entity_type, entity_id=entity_id, event_type=event_type, details=details,
                          facility_id=facility_id, actor_id=actor.id if actor else None,
                          actor_name=actor.name if actor else "system"))


class MaintenanceService:
    @staticmethod
    def get(db: Session, ticket_id) -> MaintenanceTicket:
        t = db.get(MaintenanceTicket, ticket_id)
        if not t:
            _bad("Maintenance ticket not found", 404)
        return t

    @staticmethod
    def _note(db, t: MaintenanceTicket, user: Optional[User], body: str, kind="NOTE", evidence=None):
        db.add(MaintenanceNote(ticket_id=t.id, kind=kind, body=body, evidence_reference=evidence,
                               author_id=user.id if user else None, author_name=user.name if user else "system"))

    @classmethod
    def _transition(cls, db, t: MaintenanceTicket, to: MaintenanceStatus, user: Optional[User], note: str):
        if to not in TRANSITIONS[t.status]:
            _bad(f"Invalid work-order transition {t.status.value} -> {to.value}")
        frm = t.status
        t.status = to
        cls._note(db, t, user, f"{frm.value} → {to.value}" + (f": {note}" if note else ""), kind="STATUS")
        if user:
            log_audit(db, user, f"WORK_ORDER_{to.value}", "MaintenanceTicket", t.id,
                      {"ticket": t.ticket_number, "from": frm.value, "note": note}, facility_id=t.facility_id,
                      commit=False)

    @staticmethod
    def _publish(t: MaintenanceTicket):
        realtime.publish("maintenance.updated", {"id": t.id, "ticket_number": t.ticket_number, "status": t.status,
                                                 "priority": t.priority, "assigned_to": t.assigned_to,
                                                 "title": t.title}, facility_id=t.facility_id)

    @classmethod
    def create(cls, db: Session, user: Optional[User], *, facility_id, title: str, description: str,
               storage_unit_id=None, sensor_id=None, incident_id=None,
               priority=MaintenancePriority.MEDIUM, maintenance_type=MaintenanceType.CORRECTIVE,
               trigger=MaintenanceTrigger.MANUAL, trigger_rule=None, dedup_key=None, due_date=None) -> MaintenanceTicket:
        if dedup_key:
            existing = db.query(MaintenanceTicket).filter(
                MaintenanceTicket.dedup_key == dedup_key,
                MaintenanceTicket.status.in_(ACTIVE_MAINTENANCE_STATUSES + (M.RESOLVED,))).first()
            if existing:
                return existing
        if storage_unit_id:
            unit = db.get(StorageUnit, storage_unit_id)
            if not unit or unit.facility_id != facility_id:
                _bad("Storage unit does not belong to this facility")
        if sensor_id:
            sensor = db.get(Sensor, sensor_id)
            if not sensor or (sensor.storage_unit and sensor.storage_unit.facility_id != facility_id):
                _bad("Sensor does not belong to this facility")
        days = {MaintenancePriority.URGENT: 1, MaintenancePriority.HIGH: 2, MaintenancePriority.MEDIUM: 5,
                MaintenancePriority.LOW: 14}[priority]
        t = MaintenanceTicket(
            ticket_number=next_ticket_number(db), facility_id=facility_id, storage_unit_id=storage_unit_id,
            sensor_id=sensor_id, incident_id=incident_id, title=title, description=description, priority=priority,
            maintenance_type=maintenance_type, trigger=trigger, trigger_rule=trigger_rule, dedup_key=dedup_key,
            requested_by=user.id if user else None, due_date=due_date or (_now() + timedelta(days=days)))
        db.add(t)
        db.flush()
        cls._note(db, t, user, f"Ticket created ({trigger.value}{': ' + trigger_rule if trigger_rule else ''})",
                  kind="STATUS")
        if user:
            log_audit(db, user, "WORK_ORDER_CREATED", "MaintenanceTicket", t.id, {"title": title},
                      facility_id=facility_id, commit=False)
        notify_facility(db, facility_id, [Role.TECHNICIAN], f"New work order {t.ticket_number}", title,
                        level=NotificationLevel.WARNING if priority in (MaintenancePriority.HIGH, MaintenancePriority.URGENT)
                        else NotificationLevel.INFO, category="MAINTENANCE", link=f"/maintenance/{t.id}",
                        entity_type="MaintenanceTicket", entity_id=t.id, commit=False)
        db.commit()
        MAINT_TICKETS.labels(trigger=trigger.value).inc()
        cls._publish(t)
        return t

    @classmethod
    def assign(cls, db: Session, t: MaintenanceTicket, user: User, technician_id) -> MaintenanceTicket:
        from app.services.access import resolve_scope
        tech = db.get(User, technician_id)
        if not tech or tech.role != Role.TECHNICIAN or not tech.is_active:
            _bad("Assignee must be an active maintenance technician")
        if not resolve_scope(db, tech).can_access_facility(t.facility_id):
            _bad("Technician is not assigned to this facility")
        if t.status not in (M.OPEN, M.ASSIGNED):
            _bad("Only OPEN or ASSIGNED work orders can be (re)assigned")
        t.assigned_to, t.assigned_at = tech.id, _now()
        cls._transition(db, t, M.ASSIGNED, user, f"Assigned to {tech.name}")
        notify(db, [tech], f"Work order assigned: {t.ticket_number}", t.title, category="MAINTENANCE",
               link=f"/maintenance/{t.id}", entity_type="MaintenanceTicket", entity_id=t.id,
               facility_id=t.facility_id, commit=False)
        db.commit()
        cls._publish(t)
        return t

    @classmethod
    def accept(cls, db: Session, t: MaintenanceTicket, tech: User) -> MaintenanceTicket:
        if t.status != M.OPEN and not (t.status == M.ASSIGNED and t.assigned_to == tech.id):
            _bad("Only OPEN work orders can be accepted")
        if t.status == M.OPEN:
            t.assigned_to, t.assigned_at = tech.id, _now()
            cls._transition(db, t, M.ASSIGNED, tech, "Accepted by technician")
        db.commit()
        cls._publish(t)
        return t

    @classmethod
    def start(cls, db: Session, t: MaintenanceTicket, tech: User) -> MaintenanceTicket:
        if t.assigned_to != tech.id:
            _bad("Only the assigned technician can start this work order", 403)
        t.started_at = _now()
        cls._transition(db, t, M.IN_PROGRESS, tech, "Work started")
        if t.storage_unit_id:
            unit = db.get(StorageUnit, t.storage_unit_id)
            equipment_event(db, "STORAGE_UNIT", unit.id, "MAINTENANCE_STARTED", {"ticket": t.ticket_number}, tech,
                            unit.facility_id)
        db.commit()
        cls._publish(t)
        return t

    @classmethod
    def add_note(cls, db: Session, t: MaintenanceTicket, user: User, body: str, kind: str = "NOTE",
                 evidence_reference: Optional[str] = None) -> MaintenanceTicket:
        if t.status == M.CLOSED:
            _bad("Ticket is closed")
        kind = kind.upper()
        if kind not in ("NOTE", "INSPECTION", "REPAIR", "EVIDENCE"):
            _bad("kind must be NOTE | INSPECTION | REPAIR | EVIDENCE")
        cls._note(db, t, user, body, kind, evidence_reference)
        if kind == "INSPECTION":
            t.inspection_results = (t.inspection_results + "\n" if t.inspection_results else "") + body
        if kind == "REPAIR":
            t.repair_notes = (t.repair_notes + "\n" if t.repair_notes else "") + body
        db.commit()
        cls._publish(t)
        return t

    @classmethod
    def resolve(cls, db: Session, t: MaintenanceTicket, tech: User, repair_notes: str,
                next_maintenance_due: Optional[datetime]) -> MaintenanceTicket:
        if t.assigned_to != tech.id:
            _bad("Only the assigned technician can resolve this work order", 403)
        if not repair_notes:
            _bad("Repair notes are required to resolve a work order")
        t.repair_notes = (t.repair_notes + "\n" if t.repair_notes else "") + repair_notes
        t.resolved_at = _now()
        t.next_maintenance_due = next_maintenance_due
        cls._transition(db, t, M.RESOLVED, tech, repair_notes)
        if t.storage_unit_id:
            unit = db.get(StorageUnit, t.storage_unit_id)
            unit.last_service_at = _now()
            if next_maintenance_due:
                unit.next_service_due = next_maintenance_due
        notify_facility(db, t.facility_id, [Role.OPERATOR], f"Repair completed: {t.ticket_number}",
                        "Please verify the equipment is operating normally.", category="MAINTENANCE",
                        link=f"/maintenance/{t.id}", entity_type="MaintenanceTicket", entity_id=t.id, commit=False)
        db.commit()
        cls._publish(t)
        return t

    @classmethod
    def verify(cls, db: Session, t: MaintenanceTicket, user: User, ok: bool, notes: Optional[str]) -> MaintenanceTicket:
        if t.assigned_to == user.id:
            _bad("Separation of duties: the repairing technician cannot verify their own work", 403)
        if ok:
            t.verified_by, t.verified_at = user.id, _now()
            cls._transition(db, t, M.VERIFIED, user, notes or "Operation verified")
        else:
            if not notes:
                _bad("Notes are required when verification fails")
            cls._transition(db, t, M.IN_PROGRESS, user, f"Verification failed: {notes}")
        db.commit()
        cls._publish(t)
        return t

    @classmethod
    def close(cls, db: Session, t: MaintenanceTicket, user: User, notes: Optional[str]) -> MaintenanceTicket:
        t.closed_at = _now()
        cls._transition(db, t, M.CLOSED, user, notes or "Closed")
        db.commit()
        cls._publish(t)
        return t


class CalibrationService:
    @staticmethod
    def record(db: Session, user: User, *, sensor: Sensor, calibrated_at: datetime, result: CalibrationResult,
               interval_days: int = 365, reference_temperature=None, measured_temperature=None,
               offset_applied: float = 0.0, certificate_reference=None, notes=None, ticket_id=None) -> CalibrationRecord:
        cal_at = as_utc(calibrated_at)
        if cal_at > _now() + timedelta(minutes=5):
            _bad("Calibration date cannot be in the future")
        if result == CalibrationResult.ADJUSTED and offset_applied == 0:
            _bad("An ADJUSTED calibration must record the applied offset")
        rec = CalibrationRecord(
            sensor_id=sensor.id, performed_by=user.id, performed_by_name=user.name, calibrated_at=cal_at,
            due_date=cal_at + timedelta(days=interval_days), result=result,
            reference_temperature=reference_temperature, measured_temperature=measured_temperature,
            offset_applied=offset_applied, certificate_reference=certificate_reference, notes=notes,
            ticket_id=ticket_id)
        db.add(rec)
        sensor.last_calibrated_at = cal_at
        sensor.calibration_due_at = rec.due_date
        if result == CalibrationResult.ADJUSTED:
            sensor.calibration_offset = round((sensor.calibration_offset or 0) + offset_applied, 3)
        if result == CalibrationResult.FAIL:
            sensor.status = SensorStatus.ERROR
        elif sensor.status == SensorStatus.CALIBRATING:
            sensor.status = SensorStatus.ONLINE
        facility_id = sensor.storage_unit.facility_id if sensor.storage_unit else None
        equipment_event(db, "SENSOR", sensor.id, "CALIBRATED",
                        {"result": result.value, "offset": offset_applied, "certificate": certificate_reference},
                        user, facility_id)
        log_audit(db, user, "CALIBRATION_RECORDED", "Sensor", sensor.id,
                  {"result": result.value, "offset": offset_applied, "certificate": certificate_reference},
                  facility_id=facility_id, commit=False)
        db.commit()
        return rec


class EquipmentService:
    @staticmethod
    def replace_sensor(db: Session, user: User, old: Sensor, *, new_sensor_code: str, serial_number=None,
                       reason: str, ticket_id=None) -> Sensor:
        if old.status == SensorStatus.DECOMMISSIONED:
            _bad("Sensor is already decommissioned")
        if db.query(Sensor).filter(Sensor.sensor_code == new_sensor_code).first():
            _bad("A sensor with this code already exists", 409)
        unit = old.storage_unit
        new = Sensor(sensor_code=new_sensor_code, storage_unit_id=old.storage_unit_id, sensor_type=old.sensor_type,
                     status=SensorStatus.PROVISIONED, serial_number=serial_number, manufacturer=old.manufacturer,
                     provisioned_at=_now(), is_simulated=old.is_simulated,
                     calibration_due_at=_now() + timedelta(days=365), device_key_hash=old.device_key_hash)
        db.add(new)
        old.status = SensorStatus.DECOMMISSIONED
        old.decommissioned_at = _now()
        old_unit_id = old.storage_unit_id
        old.storage_unit_id = None
        db.flush()
        fid = unit.facility_id if unit else None
        equipment_event(db, "SENSOR", old.id, "REPLACED", {"replacement": new_sensor_code, "reason": reason,
                                                            "storage_unit_id": str(old_unit_id)}, user, fid)
        equipment_event(db, "SENSOR", new.id, "INSTALLED_AS_REPLACEMENT", {"replaces": old.sensor_code}, user, fid)
        log_audit(db, user, "SENSOR_REPLACED", "Sensor", old.id, {"new_sensor": new_sensor_code, "reason": reason},
                  facility_id=fid, commit=False)
        if ticket_id:
            t = db.get(MaintenanceTicket, ticket_id)
            if t:
                MaintenanceService._note(db, t, user, f"Sensor {old.sensor_code} replaced by {new_sensor_code}", "REPAIR")
        db.commit()
        return new

    @staticmethod
    def replace_storage_unit(db: Session, user: User, old: StorageUnit, *, new_unit_code: str, name: str,
                             manufacturer=None, model=None, serial_number=None, reason: str) -> StorageUnit:
        """Install a replacement refrigerator: new unit inherits facility/policy, sensors move
        across, active stock is transferred through the inventory ledger."""
        from app.services.inventory import InventoryService
        if old.status == StorageUnitStatus.INACTIVE:
            _bad("Storage unit is already inactive")
        if db.query(StorageUnit).filter(StorageUnit.unit_code == new_unit_code).first():
            _bad("A storage unit with this code already exists", 409)
        new = StorageUnit(unit_code=new_unit_code, name=name, location=old.location, unit_type=old.unit_type,
                          min_temperature=old.min_temperature, max_temperature=old.max_temperature,
                          facility_id=old.facility_id, policy_id=old.policy_id, manufacturer=manufacturer,
                          model=model, serial_number=serial_number, installed_at=_now(),
                          next_service_due=_now() + timedelta(days=180))
        db.add(new)
        db.flush()
        moved = []
        for s in list(old.sensors):
            if s.status != SensorStatus.DECOMMISSIONED:
                s.storage_unit_id = new.id
                moved.append(s.sensor_code)
        for b in db.query(Batch).filter(Batch.storage_unit_id == old.id, Batch.status.in_(["ACTIVE", "QUARANTINED"])).all():
            qty = b.current_quantity
            InventoryService._move(db, b, MovementType.TRANSFER_OUT, -qty, user, reason=f"Equipment replacement: {reason}",
                                   from_unit=old.id, to_unit=new.id, status_after=b.status)
            b.storage_unit_id = new.id
            b.start_time = _now()
            InventoryService._move(db, b, MovementType.TRANSFER_IN, qty, user, reason=f"Equipment replacement: {reason}",
                                   from_unit=old.id, to_unit=new.id, status_after=b.status)
        old.status = StorageUnitStatus.INACTIVE
        equipment_event(db, "STORAGE_UNIT", old.id, "REPLACED", {"replacement": new_unit_code, "reason": reason,
                                                                  "sensors_moved": moved}, user, old.facility_id)
        equipment_event(db, "STORAGE_UNIT", new.id, "INSTALLED_AS_REPLACEMENT", {"replaces": old.unit_code}, user,
                        old.facility_id)
        log_audit(db, user, "STORAGE_UNIT_REPLACED", "StorageUnit", old.id, {"new_unit": new_unit_code, "reason": reason},
                  facility_id=old.facility_id, commit=False)
        db.commit()
        return new


class MaintenanceRules:
    """Deterministic, rule-based auto-ticketing (plus one clearly labelled ML trigger)."""
    LOW_BATTERY = 20.0
    CALIBRATION_LEAD_DAYS = 14
    REPEATED_EXCURSIONS = 3
    REPEATED_FAILURES = 2
    WINDOW_DAYS = 7
    ML_INSTABILITY_ANOMALIES = 8

    @classmethod
    def run(cls, db: Session) -> dict:
        created = {"offline": 0, "battery": 0, "calibration": 0, "excursions": 0, "failures": 0, "ml": 0, "service": 0}
        now = _now()
        since = now - timedelta(days=cls.WINDOW_DAYS)

        def make(key, **kw):
            before = db.query(MaintenanceTicket).filter(MaintenanceTicket.dedup_key == key).count()
            t = MaintenanceService.create(db, None, dedup_key=key, **kw)
            return int(db.query(MaintenanceTicket).filter(MaintenanceTicket.dedup_key == key).count() > before), t

        # 1. offline sensors with an active offline incident
        for inc in db.query(Incident).filter(Incident.incident_type == IncidentType.SENSOR_OFFLINE,
                                             Incident.status.notin_(["RESOLVED", "CLOSED"])).all():
            n, _ = make(f"RULE:OFFLINE:{inc.sensor_id}", facility_id=inc.facility_id, storage_unit_id=inc.storage_unit_id,
                        sensor_id=inc.sensor_id, incident_id=inc.id, title=f"Restore connectivity: {inc.title}",
                        description="Rule: sensor offline beyond policy threshold. Check power, battery, network.",
                        priority=MaintenancePriority.HIGH, trigger=MaintenanceTrigger.RULE, trigger_rule="SENSOR_OFFLINE")
            created["offline"] += n
        # 2. low battery
        for s in db.query(Sensor).filter(Sensor.battery_level.isnot(None), Sensor.battery_level < cls.LOW_BATTERY,
                                         Sensor.status != SensorStatus.DECOMMISSIONED, Sensor.storage_unit_id.isnot(None)).all():
            n, _ = make(f"RULE:BATTERY:{s.id}", facility_id=s.storage_unit.facility_id, storage_unit_id=s.storage_unit_id,
                        sensor_id=s.id, title=f"Replace battery: {s.sensor_code} ({s.battery_level:.0f}%)",
                        description=f"Rule: battery below {cls.LOW_BATTERY:.0f}%.", priority=MaintenancePriority.MEDIUM,
                        maintenance_type=MaintenanceType.PREVENTIVE, trigger=MaintenanceTrigger.RULE, trigger_rule="LOW_BATTERY")
            created["battery"] += n
        # 3. calibration due
        lead = now + timedelta(days=cls.CALIBRATION_LEAD_DAYS)
        for s in db.query(Sensor).filter(Sensor.calibration_due_at.isnot(None), Sensor.calibration_due_at <= lead,
                                         Sensor.status != SensorStatus.DECOMMISSIONED, Sensor.storage_unit_id.isnot(None)).all():
            overdue = as_utc(s.calibration_due_at) < now
            n, _ = make(f"RULE:CAL:{s.id}:{as_utc(s.calibration_due_at).date()}", facility_id=s.storage_unit.facility_id,
                        storage_unit_id=s.storage_unit_id, sensor_id=s.id,
                        title=f"{'OVERDUE ' if overdue else ''}Calibration: {s.sensor_code}",
                        description=f"Rule: calibration due {as_utc(s.calibration_due_at).date()}.",
                        priority=MaintenancePriority.HIGH if overdue else MaintenancePriority.MEDIUM,
                        maintenance_type=MaintenanceType.CALIBRATION, trigger=MaintenanceTrigger.PREVENTIVE,
                        trigger_rule="CALIBRATION_DUE", due_date=as_utc(s.calibration_due_at))
            created["calibration"] += n
        # 4. preventive service due
        for u in db.query(StorageUnit).filter(StorageUnit.status == StorageUnitStatus.ACTIVE,
                                              StorageUnit.next_service_due.isnot(None),
                                              StorageUnit.next_service_due <= lead).all():
            n, _ = make(f"RULE:SERVICE:{u.id}:{as_utc(u.next_service_due).date()}", facility_id=u.facility_id,
                        storage_unit_id=u.id, title=f"Preventive service: {u.unit_code}",
                        description=f"Scheduled service due {as_utc(u.next_service_due).date()}.",
                        priority=MaintenancePriority.LOW, maintenance_type=MaintenanceType.PREVENTIVE,
                        trigger=MaintenanceTrigger.PREVENTIVE, trigger_rule="SERVICE_DUE",
                        due_date=as_utc(u.next_service_due))
            created["service"] += n
        # 5. repeated excursions / repeated failures per unit
        from app.models import Violation
        rows = (db.query(Violation.storage_unit_id, func.count(Violation.id))
                .filter(Violation.start_time >= since).group_by(Violation.storage_unit_id).all())
        for unit_id, count in rows:
            if count >= cls.REPEATED_EXCURSIONS:
                u = db.get(StorageUnit, unit_id)
                n, _ = make(f"RULE:REPEAT_EXC:{unit_id}", facility_id=u.facility_id, storage_unit_id=unit_id,
                            title=f"Investigate repeated excursions: {u.unit_code}",
                            description=f"Rule: {count} temperature excursions in {cls.WINDOW_DAYS} days.",
                            priority=MaintenancePriority.HIGH, maintenance_type=MaintenanceType.INSPECTION,
                            trigger=MaintenanceTrigger.RULE, trigger_rule="REPEATED_EXCURSIONS")
                created["excursions"] += n
        rows = (db.query(Incident.storage_unit_id, func.count(Incident.id))
                .filter(Incident.created_at >= since,
                        Incident.incident_type.in_([IncidentType.SENSOR_OFFLINE, IncidentType.EQUIPMENT_FAILURE]))
                .group_by(Incident.storage_unit_id).all())
        for unit_id, count in rows:
            if unit_id and count >= cls.REPEATED_FAILURES:
                u = db.get(StorageUnit, unit_id)
                n, _ = make(f"RULE:REPEAT_FAIL:{unit_id}", facility_id=u.facility_id, storage_unit_id=unit_id,
                            title=f"Repeated equipment failures: {u.unit_code}",
                            description=f"Rule: {count} offline/failure incidents in {cls.WINDOW_DAYS} days.",
                            priority=MaintenancePriority.HIGH, maintenance_type=MaintenanceType.INSPECTION,
                            trigger=MaintenanceTrigger.RULE, trigger_rule="REPEATED_FAILURES")
                created["failures"] += n
        # 6. ML instability (model-based signal, labelled ML)
        day = now - timedelta(hours=24)
        rows = (db.query(Anomaly.storage_unit_id, func.count(Anomaly.id)).filter(Anomaly.detected_at >= day)
                .group_by(Anomaly.storage_unit_id).all())
        for unit_id, count in rows:
            if unit_id and count >= cls.ML_INSTABILITY_ANOMALIES:
                u = db.get(StorageUnit, unit_id)
                n, _ = make(f"ML:INSTABILITY:{unit_id}", facility_id=u.facility_id, storage_unit_id=unit_id,
                            title=f"Possible equipment instability: {u.unit_code}",
                            description=(f"ML/statistical signal: {count} anomalous readings in 24h. "
                                         "Decision support — inspect compressor, door seal and thermostat."),
                            priority=MaintenancePriority.MEDIUM, maintenance_type=MaintenanceType.INSPECTION,
                            trigger=MaintenanceTrigger.ML, trigger_rule="ANOMALY_CLUSTER_24H")
                created["ml"] += n
        return created


def maintenance_due_soon(db: Session, scope, days: int = 30):
    lead = _now() + timedelta(days=days)
    units = scope.apply(db.query(StorageUnit).filter(StorageUnit.next_service_due.isnot(None),
                                                     StorageUnit.next_service_due <= lead),
                        StorageUnit.facility_id).all()
    sensors = scope.apply(db.query(Sensor).join(StorageUnit, Sensor.storage_unit_id == StorageUnit.id)
                          .filter(Sensor.calibration_due_at.isnot(None), Sensor.calibration_due_at <= lead),
                          StorageUnit.facility_id).all()
    return units, sensors


def ticket_dict_ids(t: MaintenanceTicket) -> dict:
    return {"id": t.id, "ticket_number": t.ticket_number}


_ = uuid  # keep import for typing in callers
