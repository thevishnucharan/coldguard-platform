import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models import Facility, MonitoringPolicy, StorageUnit, TemperatureReading
from app.models.enums import StorageUnitStatus
from app.schemas.org import StorageUnitIn, StorageUnitOut, StorageUnitUpdate
from app.services.access import AccessScope
from app.services.audit import log_audit
from app.services.maintenance import equipment_event

router = APIRouter()


def _get(db, unit_id, scope) -> StorageUnit:
    u = db.get(StorageUnit, unit_id)
    if not u:
        raise HTTPException(404, "Storage unit not found")
    scope.ensure(u.facility_id, not_found="Storage unit not found")
    return u


@router.get("", response_model=List[StorageUnitOut])
def list_units(facility_id: Optional[uuid.UUID] = None, status: Optional[StorageUnitStatus] = None,
               db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("monitoring.view"))):
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(StorageUnit), StorageUnit.facility_id)
    if facility_id:
        q = q.filter(StorageUnit.facility_id == facility_id)
    if status:
        q = q.filter(StorageUnit.status == status)
    return q.order_by(StorageUnit.unit_code).all()


@router.post("", response_model=StorageUnitOut, status_code=201)
def create_unit(body: StorageUnitIn, request: Request, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("storage.manage"))):
    if not db.get(Facility, body.facility_id):
        raise HTTPException(400, "Facility not found")
    if db.query(StorageUnit).filter(StorageUnit.unit_code == body.unit_code).first():
        raise HTTPException(409, "Storage unit code already exists")
    data = body.model_dump()
    if body.policy_id:
        p = db.get(MonitoringPolicy, body.policy_id)
        if not p:
            raise HTTPException(400, "Monitoring policy not found")
        data["min_temperature"], data["max_temperature"] = p.min_temperature, p.max_temperature
    u = StorageUnit(**data)
    db.add(u)
    db.flush()
    equipment_event(db, "STORAGE_UNIT", u.id, "REGISTERED", {"unit_code": u.unit_code}, scope.user, u.facility_id)
    log_audit(db, scope.user, "STORAGE_UNIT_CREATED", "StorageUnit", u.id, {"unit_code": u.unit_code},
              category="CONFIG", facility_id=u.facility_id, request=request, commit=False)
    db.commit()
    return u


@router.get("/{unit_id}", response_model=StorageUnitOut)
def get_unit(unit_id: uuid.UUID, db: Session = Depends(get_db),
             scope: AccessScope = Depends(require_permission("monitoring.view"))):
    return _get(db, unit_id, scope)


@router.put("/{unit_id}", response_model=StorageUnitOut)
def update_unit(unit_id: uuid.UUID, body: StorageUnitUpdate, request: Request, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("storage.manage"))):
    u = _get(db, unit_id, scope)
    data = body.model_dump(exclude_unset=True)
    if data.get("policy_id"):
        p = db.get(MonitoringPolicy, data["policy_id"])
        if not p:
            raise HTTPException(400, "Monitoring policy not found")
        u.min_temperature, u.max_temperature = p.min_temperature, p.max_temperature
    for k, v in data.items():
        setattr(u, k, v)
    log_audit(db, scope.user, "STORAGE_UNIT_UPDATED", "StorageUnit", u.id, {k: str(v) for k, v in data.items()},
              category="CONFIG", facility_id=u.facility_id, request=request, commit=False)
    db.commit()
    return u


@router.delete("/{unit_id}")
def deactivate_unit(unit_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("storage.manage"))):
    """Units are never hard-deleted (history must remain traceable); they are deactivated."""
    u = _get(db, unit_id, scope)
    u.status = StorageUnitStatus.INACTIVE
    equipment_event(db, "STORAGE_UNIT", u.id, "DEACTIVATED", {}, scope.user, u.facility_id)
    log_audit(db, scope.user, "STORAGE_UNIT_DEACTIVATED", "StorageUnit", u.id, {}, category="CONFIG",
              facility_id=u.facility_id, request=request, commit=False)
    db.commit()
    return {"message": "Storage unit deactivated"}


@router.get("/{unit_id}/readings")
def unit_readings(unit_id: uuid.UUID, hours: int = Query(24, ge=1, le=24 * 31),
                  start: Optional[datetime] = None, end: Optional[datetime] = None,
                  max_points: int = Query(600, ge=10, le=5000), db: Session = Depends(get_db),
                  scope: AccessScope = Depends(require_permission("monitoring.view"))) -> Any:
    u = _get(db, unit_id, scope)
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(hours=hours)
    rows = (db.query(TemperatureReading.timestamp, TemperatureReading.temperature, TemperatureReading.quality_status,
                     TemperatureReading.is_simulated, TemperatureReading.sensor_id)
            .filter(TemperatureReading.storage_unit_id == u.id, TemperatureReading.timestamp >= start,
                    TemperatureReading.timestamp <= end).order_by(TemperatureReading.timestamp).all())
    stride = max(1, len(rows) // max_points)
    pts = rows[::stride]
    temps = [r.temperature for r in rows]
    return {"storage_unit_id": u.id, "unit_code": u.unit_code, "min_limit": u.effective_min, "max_limit": u.effective_max,
            "warning_margin": u.policy.warning_margin if u.policy else 0.5, "start": start, "end": end,
            "count": len(rows), "downsampled": stride > 1,
            "stats": {"min": min(temps), "max": max(temps), "mean": round(sum(temps) / len(temps), 2)} if temps else None,
            "points": [{"t": r.timestamp, "v": r.temperature, "q": r.quality_status, "sim": r.is_simulated} for r in pts]}
