import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.api.deps import get_db, require_permission
from app.models import CalibrationRecord, EquipmentEvent, Incident, MaintenanceTicket, Sensor, StorageUnit
from app.models.enums import MaintenancePriority, MaintenanceStatus, MaintenanceTrigger, MaintenanceType
from app.schemas.common import Page, paginate
from app.schemas.maintenance import (AssignIn, CalibrationIn, CalibrationOut, CloseIn, EquipmentEventOut, NoteIn,
                                     NoteOut, ResolveIn, SensorReplaceIn, TicketDetail, TicketIn, TicketOut,
                                     UnitReplaceIn, VerifyIn)
from app.services.access import AccessScope
from app.services.maintenance import CalibrationService, EquipmentService, MaintenanceService, maintenance_due_soon

router = APIRouter()      # /maintenance
calibration = APIRouter()  # /calibration
equipment = APIRouter()    # /equipment


def _ticket(db, ticket_id, scope) -> MaintenanceTicket:
    t = db.get(MaintenanceTicket, ticket_id)
    if not t:
        raise HTTPException(404, "Maintenance ticket not found")
    scope.ensure(t.facility_id, not_found="Maintenance ticket not found")
    return t


def _detail(db, t) -> dict:
    db.refresh(t)
    d = ser.ticket(t)
    d["notes"] = [NoteOut.model_validate(n).model_dump() for n in t.notes]
    return d


@router.get("/tickets", response_model=Page[TicketOut])
def list_tickets(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200),
                 status: Optional[List[MaintenanceStatus]] = Query(None), mine: bool = False,
                 priority: Optional[MaintenancePriority] = None, maintenance_type: Optional[MaintenanceType] = None,
                 trigger: Optional[MaintenanceTrigger] = None, facility_id: Optional[uuid.UUID] = None,
                 storage_unit_id: Optional[uuid.UUID] = None, overdue: Optional[bool] = None,
                 db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("maintenance.view"))) -> Any:
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(MaintenanceTicket), MaintenanceTicket.facility_id)
    if status:
        q = q.filter(MaintenanceTicket.status.in_(status))
    if mine:
        q = q.filter(MaintenanceTicket.assigned_to == scope.user.id)
    for col, val in ((MaintenanceTicket.priority, priority), (MaintenanceTicket.maintenance_type, maintenance_type),
                     (MaintenanceTicket.trigger, trigger), (MaintenanceTicket.facility_id, facility_id),
                     (MaintenanceTicket.storage_unit_id, storage_unit_id)):
        if val:
            q = q.filter(col == val)
    items = q.order_by(MaintenanceTicket.created_at.desc()).all() if overdue else None
    if overdue:
        rows = [ser.ticket(t) for t in items if ser.ticket(t)["is_overdue"]]
        return {"items": rows[(page - 1) * page_size: page * page_size], "total": len(rows), "page": page,
                "page_size": page_size}
    items, total = paginate(q.order_by(MaintenanceTicket.created_at.desc()), page, page_size)
    return {"items": [ser.ticket(t) for t in items], "total": total, "page": page, "page_size": page_size}


@router.post("/tickets", response_model=TicketDetail, status_code=201)
def create_ticket(body: TicketIn, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("maintenance.create"))):
    scope.ensure_requested(body.facility_id)
    if body.incident_id:
        inc = db.get(Incident, body.incident_id)
        if not inc or inc.facility_id != body.facility_id:
            raise HTTPException(400, "Incident does not belong to this facility")
    t = MaintenanceService.create(db, scope.user, **body.model_dump())
    return _detail(db, t)


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
def get_ticket(ticket_id: uuid.UUID, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("maintenance.view"))):
    return _detail(db, _ticket(db, ticket_id, scope))


@router.post("/tickets/{ticket_id}/assign", response_model=TicketDetail)
def assign(ticket_id: uuid.UUID, body: AssignIn, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("maintenance.assign"))):
    return _detail(db, MaintenanceService.assign(db, _ticket(db, ticket_id, scope), scope.user, body.technician_id))


@router.post("/tickets/{ticket_id}/accept", response_model=TicketDetail)
def accept(ticket_id: uuid.UUID, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("maintenance.update"))):
    return _detail(db, MaintenanceService.accept(db, _ticket(db, ticket_id, scope), scope.user))


@router.post("/tickets/{ticket_id}/start", response_model=TicketDetail)
def start(ticket_id: uuid.UUID, db: Session = Depends(get_db),
          scope: AccessScope = Depends(require_permission("maintenance.update"))):
    return _detail(db, MaintenanceService.start(db, _ticket(db, ticket_id, scope), scope.user))


@router.post("/tickets/{ticket_id}/notes", response_model=TicketDetail)
def add_note(ticket_id: uuid.UUID, body: NoteIn, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("maintenance.update"))):
    return _detail(db, MaintenanceService.add_note(db, _ticket(db, ticket_id, scope), scope.user, body.body, body.kind,
                                                   body.evidence_reference))


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketDetail)
def resolve(ticket_id: uuid.UUID, body: ResolveIn, db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("maintenance.update"))):
    return _detail(db, MaintenanceService.resolve(db, _ticket(db, ticket_id, scope), scope.user, body.repair_notes,
                                                  body.next_maintenance_due))


@router.post("/tickets/{ticket_id}/verify", response_model=TicketDetail)
def verify(ticket_id: uuid.UUID, body: VerifyIn, db: Session = Depends(get_db),
           scope: AccessScope = Depends(require_permission("maintenance.verify"))):
    return _detail(db, MaintenanceService.verify(db, _ticket(db, ticket_id, scope), scope.user, body.ok, body.notes))


@router.post("/tickets/{ticket_id}/close", response_model=TicketDetail)
def close(ticket_id: uuid.UUID, body: CloseIn, db: Session = Depends(get_db),
          scope: AccessScope = Depends(require_permission("maintenance.verify"))):
    return _detail(db, MaintenanceService.close(db, _ticket(db, ticket_id, scope), scope.user, body.notes))


@router.get("/schedule")
def schedule(days: int = Query(60, ge=1, le=365), db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("maintenance.view"))):
    """Preventive maintenance & calibration due within `days`."""
    units, sensors = maintenance_due_soon(db, scope, days)
    return {"service_due": [{"storage_unit_id": u.id, "unit_code": u.unit_code, "facility_id": u.facility_id,
                             "last_service_at": u.last_service_at, "next_service_due": u.next_service_due} for u in units],
            "calibration_due": [{"sensor_id": s.id, "sensor_code": s.sensor_code,
                                 "unit_code": s.storage_unit.unit_code if s.storage_unit else None,
                                 "facility_id": s.storage_unit.facility_id if s.storage_unit else None,
                                 "last_calibrated_at": s.last_calibrated_at, "calibration_due_at": s.calibration_due_at}
                                for s in sensors]}


# ------------------------------------------------------------------ calibration
@calibration.get("", response_model=List[CalibrationOut])
def list_calibrations(sensor_id: Optional[uuid.UUID] = None, limit: int = Query(200, le=2000),
                      db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("calibration.view"))):
    q = (db.query(CalibrationRecord).join(Sensor, Sensor.id == CalibrationRecord.sensor_id)
         .outerjoin(StorageUnit, StorageUnit.id == Sensor.storage_unit_id))
    if not scope.is_global:
        q = scope.apply(q, StorageUnit.facility_id)
    if sensor_id:
        q = q.filter(CalibrationRecord.sensor_id == sensor_id)
    rows = q.order_by(CalibrationRecord.calibrated_at.desc()).limit(limit).all()
    return [{**CalibrationOut.model_validate(r).model_dump(), "sensor_code": r.sensor.sensor_code} for r in rows]


@calibration.post("", response_model=CalibrationOut, status_code=201)
def record_calibration(body: CalibrationIn, db: Session = Depends(get_db),
                       scope: AccessScope = Depends(require_permission("calibration.record"))):
    s = db.get(Sensor, body.sensor_id)
    if not s or not s.storage_unit:
        raise HTTPException(404, "Sensor not found")
    scope.ensure(s.storage_unit.facility_id, not_found="Sensor not found")
    data = body.model_dump()
    data.pop("sensor_id")
    rec = CalibrationService.record(db, scope.user, sensor=s, **data)
    return {**CalibrationOut.model_validate(rec).model_dump(), "sensor_code": s.sensor_code}


# ------------------------------------------------------------------ equipment replacement / history
@equipment.post("/replace-sensor")
def replace_sensor(body: SensorReplaceIn, db: Session = Depends(get_db),
                   scope: AccessScope = Depends(require_permission("equipment.replace"))):
    old = db.get(Sensor, body.old_sensor_id)
    if not old or not old.storage_unit:
        raise HTTPException(404, "Sensor not found")
    scope.ensure(old.storage_unit.facility_id, not_found="Sensor not found")
    new = EquipmentService.replace_sensor(db, scope.user, old, new_sensor_code=body.new_sensor_code,
                                          serial_number=body.serial_number, reason=body.reason, ticket_id=body.ticket_id)
    return {"old_sensor_id": old.id, "new_sensor_id": new.id, "new_sensor_code": new.sensor_code,
            "message": "Sensor replaced; new device is PROVISIONED until it reports"}


@equipment.post("/replace-storage-unit")
def replace_unit(body: UnitReplaceIn, db: Session = Depends(get_db),
                 scope: AccessScope = Depends(require_permission("equipment.replace"))):
    old = db.get(StorageUnit, body.old_storage_unit_id)
    if not old:
        raise HTTPException(404, "Storage unit not found")
    scope.ensure(old.facility_id, not_found="Storage unit not found")
    new = EquipmentService.replace_storage_unit(db, scope.user, old, new_unit_code=body.new_unit_code, name=body.name,
                                                manufacturer=body.manufacturer, model=body.model,
                                                serial_number=body.serial_number, reason=body.reason)
    return {"old_storage_unit_id": old.id, "new_storage_unit_id": new.id, "new_unit_code": new.unit_code}


@equipment.get("/history", response_model=List[EquipmentEventOut])
def history(entity_id: Optional[uuid.UUID] = None, facility_id: Optional[uuid.UUID] = None,
            limit: int = Query(200, le=2000), db: Session = Depends(get_db),
            scope: AccessScope = Depends(require_permission("maintenance.view"))):
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(EquipmentEvent), EquipmentEvent.facility_id)
    if entity_id:
        q = q.filter(EquipmentEvent.entity_id == entity_id)
    if facility_id:
        q = q.filter(EquipmentEvent.facility_id == facility_id)
    return q.order_by(EquipmentEvent.created_at.desc()).limit(limit).all()
