"""Sensor health (preserved v1 per-reading checks) + connectivity sweep.

Distinguishes:
  MISSING_TELEMETRY  no reading for > policy.missing_telemetry_minutes (sensor may still be
                     connected; gap in data)  -> WARNING incident
  SENSOR_OFFLINE     no reading for > policy.offline_minutes -> sensor marked OFFLINE,
                     HIGH incident (+ rule-based maintenance ticket via MaintenanceRules)
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.base import as_utc
from app.models import Incident, Sensor, SensorHealthEvent, StorageUnit, TemperatureReading
from app.models.enums import (ACTIVE_INCIDENT_STATUSES, IncidentType, SensorHealthState, SensorStatus,
                              StorageUnitStatus, ViolationSeverity)
from app.services import realtime

logger = logging.getLogger(__name__)

DEFAULT_MISSING_MIN = 5
DEFAULT_OFFLINE_MIN = 15


def thresholds(unit: StorageUnit | None) -> tuple[int, int]:
    if unit is not None and unit.policy is not None:
        return unit.policy.missing_telemetry_minutes, unit.policy.offline_minutes
    return DEFAULT_MISSING_MIN, DEFAULT_OFFLINE_MIN


class SensorHealthService:
    CONSTANT_TEMP_COUNT = 5
    UNREALISTIC_JUMP_THRESHOLD = 15.0
    MAX_VALID_TEMP = 60.0
    MIN_VALID_TEMP = -90.0
    OFFLINE_THRESHOLD_MINUTES = DEFAULT_OFFLINE_MIN

    @classmethod
    def evaluate_reading(cls, db: Session, reading: TemperatureReading):
        previous = (db.query(TemperatureReading)
                    .filter(TemperatureReading.sensor_id == reading.sensor_id, TemperatureReading.id != reading.id)
                    .order_by(desc(TemperatureReading.timestamp)).limit(cls.CONSTANT_TEMP_COUNT).all())
        if reading.temperature > cls.MAX_VALID_TEMP or reading.temperature < cls.MIN_VALID_TEMP:
            cls._create_event(db, reading.sensor_id, "INVALID_TEMPERATURE", SensorHealthState.CRITICAL,
                              f"Temp {reading.temperature} is physically unrealistic")
            return
        if not previous:
            return
        last = previous[0]
        diff_s = (as_utc(reading.timestamp) - as_utc(last.timestamp)).total_seconds()
        if 0 < diff_s < 5:
            cls._create_event(db, reading.sensor_id, "ABNORMAL_FREQUENCY", SensorHealthState.WARNING,
                              f"Readings received too fast ({diff_s:.0f}s apart)")
        jump = abs(reading.temperature - last.temperature)
        if jump >= cls.UNREALISTIC_JUMP_THRESHOLD:
            cls._create_event(db, reading.sensor_id, "UNREALISTIC_JUMP", SensorHealthState.CRITICAL,
                              f"Jumped {jump:.1f} degrees between consecutive readings")
        if len(previous) == cls.CONSTANT_TEMP_COUNT:
            temps = {reading.temperature} | {r.temperature for r in previous}
            if len(temps) == 1:
                cls._create_event(db, reading.sensor_id, "POSSIBLE_STUCK_SENSOR", SensorHealthState.WARNING,
                                  f"Temperature stuck at {reading.temperature} for {cls.CONSTANT_TEMP_COUNT + 1} readings")

    @classmethod
    def on_sensor_recovered(cls, db: Session, sensor: Sensor):
        cls._create_event(db, sensor.id, "SENSOR_RECOVERED", SensorHealthState.HEALTHY, "Telemetry resumed")
        from app.services.incident import IncidentService
        for inc in (db.query(Incident).filter(
                Incident.sensor_id == sensor.id,
                Incident.incident_type.in_([IncidentType.SENSOR_OFFLINE, IncidentType.MISSING_TELEMETRY]),
                Incident.status.in_(ACTIVE_INCIDENT_STATUSES))):
            IncidentService.record_system_event(db, inc, "TELEMETRY_RESTORED",
                                                "Sensor is reporting again. Operator verification still required.")
        _publish_sensor(sensor)

    @classmethod
    def check_offline_sensors(cls, db: Session, now: datetime | None = None) -> dict:
        """Sweep run by the worker. Returns counts for observability/tests."""
        from app.services.incident import IncidentService
        now = now or datetime.now(timezone.utc)
        stats = {"missing": 0, "offline": 0}
        sensors = (db.query(Sensor).join(StorageUnit, Sensor.storage_unit_id == StorageUnit.id)
                   .filter(Sensor.status.in_([SensorStatus.ONLINE, SensorStatus.OFFLINE, SensorStatus.PROVISIONED]),
                           StorageUnit.status == StorageUnitStatus.ACTIVE).all())
        for s in sensors:
            unit = s.storage_unit
            missing_min, offline_min = thresholds(unit)
            last = as_utc(s.last_reading_at) or as_utc(s.provisioned_at) or as_utc(s.created_at)
            if last is None:
                continue
            silent = (now - last).total_seconds() / 60.0
            key = f"CONNECTIVITY:{s.id}"
            active = (db.query(Incident).filter(Incident.dedup_key == key,
                                                Incident.status.in_(ACTIVE_INCIDENT_STATUSES)).first())
            if silent >= offline_min:
                if s.status != SensorStatus.OFFLINE:
                    s.status = SensorStatus.OFFLINE
                    cls._create_event(db, s.id, "SENSOR_OFFLINE", SensorHealthState.OFFLINE,
                                      f"No reading for {silent:.0f} min (offline threshold {offline_min} min)")
                    _publish_sensor(s)
                desc_txt = (f"No telemetry from {s.sensor_code} on {unit.unit_code} for {silent:.0f} minutes. "
                            "Storage temperature is currently UNKNOWN.")
                if active is None:
                    IncidentService.open_incident(
                        db, incident_type=IncidentType.SENSOR_OFFLINE, severity=ViolationSeverity.HIGH,
                        facility_id=unit.facility_id, storage_unit_id=unit.id, sensor_id=s.id,
                        title=f"Sensor {s.sensor_code} offline", description=desc_txt,
                        dedup_key=key, is_simulated=s.is_simulated)
                    stats["offline"] += 1
                elif active.incident_type == IncidentType.MISSING_TELEMETRY:
                    # escalate the existing missing-telemetry incident instead of opening a second one
                    active.incident_type = IncidentType.SENSOR_OFFLINE
                    active.title = f"Sensor {s.sensor_code} offline"
                    IncidentService.record_system_event(db, active, "SENSOR_OFFLINE", desc_txt, commit=False)
                    IncidentService.raise_severity(db, active, ViolationSeverity.HIGH, "Sensor now considered offline")
                    stats["offline"] += 1
            elif silent >= missing_min and active is None:
                IncidentService.open_incident(
                    db, incident_type=IncidentType.MISSING_TELEMETRY, severity=ViolationSeverity.WARNING,
                    facility_id=unit.facility_id, storage_unit_id=unit.id, sensor_id=s.id,
                    title=f"Missing telemetry from {s.sensor_code}",
                    description=f"Expected readings not received for {silent:.0f} min "
                                f"(threshold {missing_min} min).",
                    dedup_key=key, is_simulated=s.is_simulated)
                stats["missing"] += 1
        db.commit()
        return stats

    @classmethod
    def _create_event(cls, db: Session, sensor_id: uuid.UUID, event_type: str, state: SensorHealthState, details: str):
        db.add(SensorHealthEvent(sensor_id=sensor_id, event_type=event_type, health_state=state, details=details))
        db.commit()


def _publish_sensor(s: Sensor):
    unit = s.storage_unit
    realtime.publish("sensor.status", {"sensor_id": s.id, "sensor_code": s.sensor_code, "status": s.status,
                                       "storage_unit_id": s.storage_unit_id,
                                       "last_reading_at": s.last_reading_at},
                     facility_id=unit.facility_id if unit else None)
