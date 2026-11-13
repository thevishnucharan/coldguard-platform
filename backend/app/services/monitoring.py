"""Live monitoring read model: per-unit health with explicit staleness.

A reading is never presented as current when it is stale: every unit carries
`last_reading_at`, `seconds_since_reading` and `stale=true` once the policy's
missing-telemetry window has elapsed (health becomes MISSING_TELEMETRY / OFFLINE).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.base import as_utc
from app.models import Incident, Sensor, StorageUnit, TemperatureReading, Violation
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, SensorStatus, StorageUnitStatus, UnitHealth,
                              ViolationSeverity, ViolationStatus)
from app.services.sensor_health import thresholds

HEALTH_RANK = {UnitHealth.NORMAL: 0, UnitHealth.NO_DATA: 1, UnitHealth.INACTIVE: 0, UnitHealth.WARNING: 2,
               UnitHealth.MISSING_TELEMETRY: 3, UnitHealth.OFFLINE: 4, UnitHealth.CRITICAL: 5}


def _now():
    return datetime.now(timezone.utc)


def unit_health(unit: StorageUnit, sensors: List[Sensor], open_violation: Optional[Violation],
                now: Optional[datetime] = None) -> dict:
    now = now or _now()
    lo, hi = unit.effective_min, unit.effective_max
    margin = unit.policy.warning_margin if unit.policy else 0.5
    missing_min, offline_min = thresholds(unit)
    live = [s for s in sensors if s.status != SensorStatus.DECOMMISSIONED]
    last_ts = max((as_utc(s.last_reading_at) for s in live if s.last_reading_at), default=None)
    latest = None
    if last_ts:
        latest = next((s.last_temperature for s in live if as_utc(s.last_reading_at) == last_ts), None)
    secs = int((now - last_ts).total_seconds()) if last_ts else None
    stale = secs is None or secs >= missing_min * 60
    if unit.status != StorageUnitStatus.ACTIVE:
        health = UnitHealth.INACTIVE
    elif not live or last_ts is None:
        health = UnitHealth.NO_DATA
    elif any(s.status == SensorStatus.OFFLINE for s in live) or secs >= offline_min * 60:
        health = UnitHealth.OFFLINE
    elif stale:
        health = UnitHealth.MISSING_TELEMETRY
    elif latest is not None and (latest > hi or latest < lo):
        health = (UnitHealth.CRITICAL if open_violation is None or open_violation.severity == ViolationSeverity.CRITICAL
                  or open_violation.severity == ViolationSeverity.HIGH else UnitHealth.WARNING)
    elif latest is not None and (latest > hi - margin or latest < lo + margin):
        health = UnitHealth.WARNING
    else:
        health = UnitHealth.NORMAL
    return {"health": health.value, "latest_temperature": latest, "last_reading_at": last_ts,
            "seconds_since_reading": secs, "stale": stale}


def live_units(db: Session, scope, facility_id=None, include_sparkline: bool = True, hours: int = 3) -> List[dict]:
    q = (db.query(StorageUnit).options(joinedload(StorageUnit.sensors), joinedload(StorageUnit.policy),
                                       joinedload(StorageUnit.facility)))
    q = scope.apply(q, StorageUnit.facility_id)
    if facility_id:
        q = q.filter(StorageUnit.facility_id == facility_id)
    units = q.filter(StorageUnit.status != StorageUnitStatus.INACTIVE).order_by(StorageUnit.unit_code).all()
    if not units:
        return []
    ids = [u.id for u in units]
    open_v = {v.storage_unit_id: v for v in db.query(Violation).filter(
        Violation.storage_unit_id.in_(ids), Violation.status == ViolationStatus.OPEN)}
    inc_counts: Dict = dict(db.query(Incident.storage_unit_id, func.count(Incident.id)).filter(
        Incident.storage_unit_id.in_(ids), Incident.status.in_(ACTIVE_INCIDENT_STATUSES))
        .group_by(Incident.storage_unit_id).all())
    spark: Dict = {}
    if include_sparkline:
        since = _now() - timedelta(hours=hours)
        for uid, ts, t in (db.query(TemperatureReading.storage_unit_id, TemperatureReading.timestamp,
                                    TemperatureReading.temperature)
                           .filter(TemperatureReading.storage_unit_id.in_(ids), TemperatureReading.timestamp >= since)
                           .order_by(TemperatureReading.timestamp)):
            spark.setdefault(uid, []).append((as_utc(ts), t))
    out = []
    now = _now()
    for u in units:
        h = unit_health(u, u.sensors, open_v.get(u.id), now)
        pts = spark.get(u.id, [])
        if len(pts) > 60:  # downsample for transport
            step = len(pts) / 60
            pts = [pts[int(i * step)] for i in range(60)]
        out.append({
            "id": u.id, "unit_code": u.unit_code, "name": u.name, "unit_type": u.unit_type, "status": u.status.value,
            "facility_id": u.facility_id, "facility_name": u.facility.name if u.facility else None,
            "min_temperature": u.effective_min, "max_temperature": u.effective_max,
            "warning_margin": u.policy.warning_margin if u.policy else 0.5,
            "policy_name": u.policy.name if u.policy else None, **h,
            "active_incidents": inc_counts.get(u.id, 0),
            "sensors": [{"id": s.id, "sensor_code": s.sensor_code, "status": s.status.value,
                         "battery_level": s.battery_level, "last_reading_at": s.last_reading_at,
                         "last_temperature": s.last_temperature, "is_simulated": s.is_simulated}
                        for s in u.sensors if s.status != SensorStatus.DECOMMISSIONED],
            "is_simulated": any(s.is_simulated for s in u.sensors),
            "sparkline": [{"t": ts.isoformat(), "v": v} for ts, v in pts],
        })
    return out


def worst(healths: List[str]) -> str:
    if not healths:
        return UnitHealth.NO_DATA.value
    return max(healths, key=lambda h: HEALTH_RANK.get(UnitHealth(h), 0))
