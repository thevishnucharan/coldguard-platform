"""Device registry (sensors)."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models import EquipmentEvent, Sensor, SensorHealthEvent, StorageUnit
from app.models.enums import SensorHealthState, SensorStatus
from app.schemas.maintenance import EquipmentEventOut
from app.schemas.org import SensorOut, SensorProvision, SensorProvisioned, SensorUpdate
from app.security.auth import hash_device_key
from app.services.access import AccessScope
from app.services.audit import log_audit
from app.services.maintenance import equipment_event

router = APIRouter()


def _get(db, sensor_id, scope) -> Sensor:
    s = db.get(Sensor, sensor_id)
    if not s:
        raise HTTPException(404, "Sensor not found")
    fid = s.storage_unit.facility_id if s.storage_unit else None
    if fid is None and not scope.is_global:
        raise HTTPException(404, "Sensor not found")
    if fid is not None:
        scope.ensure(fid, not_found="Sensor not found")
    return s


@router.get("", response_model=List[SensorOut])
def list_sensors(facility_id: Optional[uuid.UUID] = None, status: Optional[SensorStatus] = None,
                 storage_unit_id: Optional[uuid.UUID] = None, include_decommissioned: bool = False,
                 db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("devices.view"))):
    scope.ensure_requested(facility_id)
    q = db.query(Sensor).outerjoin(StorageUnit, StorageUnit.id == Sensor.storage_unit_id)
    if not scope.is_global:
        q = scope.apply(q, StorageUnit.facility_id)
    if facility_id:
        q = q.filter(StorageUnit.facility_id == facility_id)
    if storage_unit_id:
        q = q.filter(Sensor.storage_unit_id == storage_unit_id)
    if status:
        q = q.filter(Sensor.status == status)
    elif not include_decommissioned:
        q = q.filter(Sensor.status != SensorStatus.DECOMMISSIONED)
    return q.order_by(Sensor.sensor_code).all()


@router.post("", response_model=SensorProvisioned, status_code=201)
def provision_sensor(body: SensorProvision, request: Request, db: Session = Depends(get_db),
                     scope: AccessScope = Depends(require_permission("devices.register"))):
    if db.query(Sensor).filter(Sensor.sensor_code == body.sensor_code).first():
        raise HTTPException(409, "Sensor code already registered")
    unit = db.get(StorageUnit, body.storage_unit_id)
    if not unit:
        raise HTTPException(400, "Storage unit not found")
    key = secrets.token_urlsafe(24)
    s = Sensor(**body.model_dump(), status=SensorStatus.PROVISIONED, provisioned_at=datetime.now(timezone.utc),
               device_key_hash=hash_device_key(key))
    if s.calibration_due_at is None:
        s.calibration_due_at = datetime.now(timezone.utc) + timedelta(days=365)
    db.add(s)
    db.flush()
    equipment_event(db, "SENSOR", s.id, "PROVISIONED", {"storage_unit": unit.unit_code}, scope.user, unit.facility_id)
    log_audit(db, scope.user, "DEVICE_PROVISIONED", "Sensor", s.id, {"sensor_code": s.sensor_code,
                                                                     "unit": unit.unit_code}, category="CONFIG",
              facility_id=unit.facility_id, request=request, commit=False)
    db.commit()
    out = SensorOut.model_validate(s).model_dump()
    out["device_key"] = key
    return out


@router.get("/health")
def sensors_health(db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("devices.view"))):
    """Preserved v1 endpoint: current health per sensor."""
    sensors = list_sensors(db=db, scope=scope)
    out = []
    for s in sensors:
        last = (db.query(SensorHealthEvent).filter(SensorHealthEvent.sensor_id == s.id)
                .order_by(desc(SensorHealthEvent.detected_at)).first())
        out.append({"sensor_id": s.id, "sensor_code": s.sensor_code, "status": s.status.value,
                    "current_health_state": (last.health_state if last else SensorHealthState.HEALTHY).value,
                    "last_event": {"event_type": last.event_type, "details": last.details,
                                   "detected_at": last.detected_at} if last else None,
                    "last_reading_at": s.last_reading_at, "battery_level": s.battery_level})
    return out


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(sensor_id: uuid.UUID, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("devices.view"))):
    return _get(db, sensor_id, scope)


@router.put("/{sensor_id}", response_model=SensorOut)
def update_sensor(sensor_id: uuid.UUID, body: SensorUpdate, request: Request, db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("devices.register"))):
    s = _get(db, sensor_id, scope)
    data = body.model_dump(exclude_unset=True)
    if data.get("status") == SensorStatus.DECOMMISSIONED:
        raise HTTPException(400, "Use the decommission endpoint")
    for k, v in data.items():
        setattr(s, k, v)
    log_audit(db, scope.user, "DEVICE_UPDATED", "Sensor", s.id, {k: str(v) for k, v in data.items()},
              category="CONFIG", request=request, commit=False)
    db.commit()
    return s


@router.post("/{sensor_id}/assign", response_model=SensorOut)
def reassign_sensor(sensor_id: uuid.UUID, storage_unit_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("devices.register"))):
    s = _get(db, sensor_id, scope)
    unit = db.get(StorageUnit, storage_unit_id)
    if not unit:
        raise HTTPException(400, "Storage unit not found")
    if s.status == SensorStatus.DECOMMISSIONED:
        raise HTTPException(400, "Decommissioned sensors cannot be reassigned")
    old = s.storage_unit.unit_code if s.storage_unit else None
    s.storage_unit_id = unit.id
    equipment_event(db, "SENSOR", s.id, "REASSIGNED", {"from": old, "to": unit.unit_code}, scope.user, unit.facility_id)
    log_audit(db, scope.user, "DEVICE_REASSIGNED", "Sensor", s.id, {"from": old, "to": unit.unit_code},
              category="CONFIG", facility_id=unit.facility_id, request=request, commit=False)
    db.commit()
    return s


@router.post("/{sensor_id}/decommission", response_model=SensorOut)
def decommission_sensor(sensor_id: uuid.UUID, reason: str = Query(..., min_length=3, max_length=500),
                        request: Request = None, db: Session = Depends(get_db),
                        scope: AccessScope = Depends(require_permission("devices.register"))):
    """Retire or block a compromised device. Its telemetry is rejected from now on; history is kept."""
    s = _get(db, sensor_id, scope)
    fid = s.storage_unit.facility_id if s.storage_unit else None
    s.status, s.decommissioned_at, s.device_key_hash = SensorStatus.DECOMMISSIONED, datetime.now(timezone.utc), None
    equipment_event(db, "SENSOR", s.id, "DECOMMISSIONED", {"reason": reason}, scope.user, fid)
    log_audit(db, scope.user, "DEVICE_DECOMMISSIONED", "Sensor", s.id, {"reason": reason}, category="SECURITY",
              facility_id=fid, request=request, commit=False)
    db.commit()
    return s


@router.post("/{sensor_id}/rotate-key")
def rotate_key(sensor_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
               scope: AccessScope = Depends(require_permission("devices.register"))):
    s = _get(db, sensor_id, scope)
    key = secrets.token_urlsafe(24)
    s.device_key_hash = hash_device_key(key)
    log_audit(db, scope.user, "DEVICE_KEY_ROTATED", "Sensor", s.id, {}, category="SECURITY", request=request,
              commit=False)
    db.commit()
    return {"sensor_id": s.id, "device_key": key}


@router.get("/{sensor_id}/health")
def sensor_health_history(sensor_id: uuid.UUID, limit: int = Query(100, le=1000), db: Session = Depends(get_db),
                          scope: AccessScope = Depends(require_permission("devices.view"))):
    _get(db, sensor_id, scope)
    return [{"id": e.id, "event_type": e.event_type, "health_state": e.health_state.value, "details": e.details,
             "detected_at": e.detected_at}
            for e in db.query(SensorHealthEvent).filter(SensorHealthEvent.sensor_id == sensor_id)
            .order_by(desc(SensorHealthEvent.detected_at)).limit(limit)]


@router.get("/{sensor_id}/history", response_model=List[EquipmentEventOut])
def sensor_history(sensor_id: uuid.UUID, db: Session = Depends(get_db),
                   scope: AccessScope = Depends(require_permission("devices.view"))):
    _get(db, sensor_id, scope)
    return (db.query(EquipmentEvent).filter(EquipmentEvent.entity_id == sensor_id)
            .order_by(EquipmentEvent.created_at.desc()).all())
