"""Excursion state machine (preserved from v1, made policy-aware).

For each valid reading:
  out of approved limits & no open violation  -> open Violation + TEMPERATURE_EXCURSION incident
  out of limits & open violation              -> extend peak/duration, re-grade severity
  back within limits & open violation         -> close Violation, record recovery on incident

Limits come from the unit's approved MonitoringPolicy (fallback: the unit's own min/max).
Severity uses the policy's critical deviation / sustained-duration settings when present,
otherwise the configurable SeverityEngine (v1).
"""
import logging

from sqlalchemy.orm import Session

from app.core.telemetry import track_metric
from app.db.base import as_utc
from app.models import Incident, StorageUnit, TemperatureReading, Violation
from app.models.enums import IncidentType, ViolationSeverity, ViolationStatus
from app.engines.severity import SeverityEngine

logger = logging.getLogger(__name__)


def grade(unit: StorageUnit, deviation: float, duration_mins: float, db: Session) -> ViolationSeverity:
    p = unit.policy
    if p is None:
        return SeverityEngine.evaluate(deviation, duration_mins, db=db)
    if deviation >= p.critical_deviation or duration_mins >= p.critical_after_minutes:
        return ViolationSeverity.CRITICAL
    if deviation >= p.critical_deviation / 2 or duration_mins >= p.critical_after_minutes / 2:
        return ViolationSeverity.HIGH
    return ViolationSeverity.WARNING


class ViolationEngine:
    @staticmethod
    def process_reading(db: Session, reading: TemperatureReading):
        if reading.quality_status == "invalid":
            return
        unit = db.get(StorageUnit, reading.storage_unit_id)
        if not unit:
            return
        lo, hi = unit.effective_min, unit.effective_max
        t = reading.temperature
        active = (db.query(Violation)
                  .filter(Violation.storage_unit_id == unit.id, Violation.status == ViolationStatus.OPEN)
                  .order_by(Violation.start_time.desc()).first())
        deviation = (t - hi) if t > hi else (lo - t) if t < lo else 0.0
        ts = as_utc(reading.timestamp)

        from app.services.incident import IncidentService

        if deviation > 0:
            v_type = "HIGH_EXCURSION" if t > hi else "LOW_EXCURSION"
            if active is None:
                sev = grade(unit, deviation, 0.0, db)
                violation = Violation(
                    storage_unit_id=unit.id, sensor_id=reading.sensor_id, start_time=ts, end_time=ts,
                    peak_temperature=t, minimum_temperature=t, allowed_minimum=lo, allowed_maximum=hi,
                    deviation=round(deviation, 3), duration_seconds=0, violation_type=v_type, severity=sev,
                    status=ViolationStatus.OPEN)
                db.add(violation)
                db.commit()
                track_metric("violations_detected", 1.0, {"unit": unit.unit_code, "severity": sev.value})
                direction = "above" if t > hi else "below"
                IncidentService.open_incident(
                    db, incident_type=IncidentType.TEMPERATURE_EXCURSION, severity=sev, facility_id=unit.facility_id,
                    storage_unit_id=unit.id, sensor_id=reading.sensor_id,
                    title=f"Temperature {direction} approved range on {unit.unit_code}",
                    description=f"{t:.1f}°C recorded; approved range {lo:.1f}–{hi:.1f}°C "
                                f"({'policy ' + unit.policy.name if unit.policy else 'unit limits'}).",
                    source="RULE", dedup_key=f"EXCURSION:{unit.id}", violation_id=violation.id,
                    is_simulated=reading.is_simulated, detected_at=ts,
                    data={"temperature": t, "limit_min": lo, "limit_max": hi, "reading_id": str(reading.id)})
            else:
                duration_mins = max(0.0, (ts - as_utc(active.start_time)).total_seconds() / 60.0)
                active.end_time = ts
                active.peak_temperature = max(active.peak_temperature, t)
                active.minimum_temperature = min(active.minimum_temperature, t)
                active.deviation = round(max(active.deviation, deviation), 3)
                active.duration_seconds = int(duration_mins * 60)
                new_sev = grade(unit, active.deviation, duration_mins, db)
                old_sev = active.severity
                active.severity = new_sev
                db.commit()
                if new_sev != old_sev:
                    inc = _incident_for(db, active)
                    if inc:
                        IncidentService.raise_severity(
                            db, inc, new_sev,
                            f"Excursion now {duration_mins:.0f} min, max deviation {active.deviation:.1f}°C")
        elif active is not None:
            active.status = ViolationStatus.RESOLVED
            active.end_time = ts
            active.duration_seconds = int(max(0.0, (ts - as_utc(active.start_time)).total_seconds()))
            db.commit()
            inc = _incident_for(db, active)
            if inc:
                IncidentService.record_system_event(
                    db, inc, "TEMPERATURE_RECOVERED",
                    f"Back within {lo:.1f}–{hi:.1f}°C at {t:.1f}°C after {active.duration_seconds // 60} min. "
                    "Investigation and supervisor review still required.",
                    data={"temperature": t, "duration_seconds": active.duration_seconds})


def _incident_for(db: Session, violation: Violation):
    inc = db.query(Incident).filter(Incident.violation_id == violation.id).first()
    if inc:
        return inc
    # repeated excursion folded into an earlier active incident (dedup)
    return (db.query(Incident).filter(Incident.dedup_key == f"EXCURSION:{violation.storage_unit_id}")
            .order_by(Incident.created_at.desc()).first())
