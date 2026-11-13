"""Telemetry ingestion pipeline (shared by MQTT, REST gateway and simulator):

  validate message -> resolve sensor identity -> idempotency check -> DataQualityEngine
  -> store reading (calibration offset applied) -> ViolationEngine (thresholds/incidents)
  -> SensorHealthService -> ML/statistical anomaly detection -> real-time push

Rejected or malformed messages are written to `telemetry_quarantine`, never silently dropped.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.metrics import (INGEST_LATENCY, TELEMETRY_ACCEPTED, TELEMETRY_DUPLICATES, TELEMETRY_RECEIVED,
                              TELEMETRY_REJECTED)
from app.engines.quality import DataQualityEngine, QualityStatus
from app.models import Sensor, TelemetryQuarantine, TemperatureReading
from app.models.enums import SensorStatus
from app.services import realtime

logger = logging.getLogger(__name__)


class TelemetryMessage(BaseModel):
    """Canonical device message. MQTT topic: coldguard/telemetry/<facility_code>/<sensor_code>"""
    sensor_code: Optional[str] = Field(None, max_length=50)
    sensor_id: Optional[uuid.UUID] = None
    storage_unit_id: Optional[uuid.UUID] = None  # accepted for v1 compatibility; must match registry
    temperature: float = Field(..., ge=-100.0, le=100.0)
    timestamp: datetime
    humidity: Optional[float] = Field(None, ge=0, le=100)
    battery: Optional[float] = Field(None, ge=0, le=100)
    message_id: Optional[str] = Field(None, max_length=100)
    simulated: bool = False
    source: Optional[str] = None

    @field_validator("timestamp")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    @model_validator(mode="after")
    def _identity(self):
        if not self.sensor_code and not self.sensor_id:
            raise ValueError("sensor_code or sensor_id is required")
        return self


@dataclass
class IngestResult:
    status: str  # accepted | duplicate | rejected
    reason: str = ""
    reading_id: Optional[uuid.UUID] = None
    quality: Optional[str] = None


def _quarantine(db: Session, channel: str, raw: Any, reason: str, sensor_code: Optional[str], simulated: bool):
    try:
        payload = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    except Exception:
        payload = str(raw)
    db.add(TelemetryQuarantine(channel=channel, sensor_code=sensor_code, raw_payload=payload[:4000],
                               reason=reason[:500], is_simulated=simulated))
    db.commit()
    TELEMETRY_REJECTED.labels(channel=channel, reason=reason.split(":")[0][:40]).inc()


def _resolve_sensor(db: Session, msg: TelemetryMessage) -> Optional[Sensor]:
    if msg.sensor_id:
        return db.get(Sensor, msg.sensor_id)
    return db.query(Sensor).filter(Sensor.sensor_code == msg.sensor_code).first()


def ingest(db: Session, raw: Union[Dict[str, Any], str, bytes], channel: str = "rest",
           run_analytics: bool = True) -> IngestResult:
    started = time.perf_counter()
    TELEMETRY_RECEIVED.labels(channel=channel).inc()
    data: Any = raw
    try:
        if isinstance(raw, (bytes, bytearray)):
            data = raw.decode("utf-8")
        if isinstance(data, str):
            data = json.loads(data)
        msg = TelemetryMessage(**data)
    except (ValueError, ValidationError, TypeError) as exc:
        code = data.get("sensor_code") if isinstance(data, dict) else None
        sim = bool(data.get("simulated")) if isinstance(data, dict) else False
        _quarantine(db, channel, raw if not isinstance(raw, bytes) else raw.decode("utf-8", "replace"),
                    f"malformed: {str(exc)[:300]}", code, sim)
        return IngestResult("rejected", "malformed payload")

    sensor = _resolve_sensor(db, msg)
    code = msg.sensor_code or (str(msg.sensor_id) if msg.sensor_id else None)
    if sensor is None:
        _quarantine(db, channel, data, "identity: unknown sensor", code, msg.simulated)
        return IngestResult("rejected", "unknown sensor")
    if sensor.status == SensorStatus.DECOMMISSIONED:
        _quarantine(db, channel, data, "identity: sensor decommissioned", sensor.sensor_code, msg.simulated)
        return IngestResult("rejected", "sensor decommissioned")
    if sensor.storage_unit_id is None:
        _quarantine(db, channel, data, "identity: sensor not assigned to a storage unit", sensor.sensor_code, msg.simulated)
        return IngestResult("rejected", "sensor unassigned")
    if msg.storage_unit_id and msg.storage_unit_id != sensor.storage_unit_id:
        _quarantine(db, channel, data, "identity: storage unit does not match device registry", sensor.sensor_code, msg.simulated)
        return IngestResult("rejected", "storage unit mismatch")

    # Idempotency: message id, then (sensor, timestamp)
    if msg.message_id and db.query(TemperatureReading.id).filter(
            TemperatureReading.sensor_id == sensor.id, TemperatureReading.message_id == msg.message_id).first():
        TELEMETRY_DUPLICATES.labels(channel=channel).inc()
        return IngestResult("duplicate", "message already processed")

    temperature = round(msg.temperature + (sensor.calibration_offset or 0.0), 3)
    quality, reason = DataQualityEngine.evaluate(db, sensor.id, temperature, msg.timestamp)
    if quality == QualityStatus.INVALID:
        if "Duplicate" in reason:
            TELEMETRY_DUPLICATES.labels(channel=channel).inc()
            return IngestResult("duplicate", reason)
        _quarantine(db, channel, data, f"quality: {reason}", sensor.sensor_code, msg.simulated)
        return IngestResult("rejected", reason)

    simulated = msg.simulated or sensor.is_simulated
    reading = TemperatureReading(
        storage_unit_id=sensor.storage_unit_id, sensor_id=sensor.id, temperature=temperature,
        timestamp=msg.timestamp, source=msg.source or channel, quality_status=quality,
        is_simulated=simulated, message_id=msg.message_id, humidity=msg.humidity, battery_level=msg.battery,
    )
    db.add(reading)
    was_offline = sensor.status in (SensorStatus.OFFLINE, SensorStatus.PROVISIONED, SensorStatus.ERROR)
    last = sensor.last_reading_at
    if last is None or (last if last.tzinfo else last.replace(tzinfo=timezone.utc)) <= msg.timestamp:
        sensor.last_reading_at = msg.timestamp
        sensor.last_temperature = temperature
    if msg.battery is not None:
        sensor.battery_level = msg.battery
    if sensor.status != SensorStatus.CALIBRATING:
        sensor.status = SensorStatus.ONLINE
    db.commit()
    TELEMETRY_ACCEPTED.labels(channel=channel, simulated=str(simulated).lower()).inc()

    if run_analytics:
        from app.engines.violation import ViolationEngine
        from app.ml.anomaly_service import MLAnomalyService
        from app.services.sensor_health import SensorHealthService
        for step, fn in (("violation", ViolationEngine.process_reading), ("health", SensorHealthService.evaluate_reading),
                         ("ml", MLAnomalyService.evaluate_reading)):
            try:
                fn(db, reading)
            except Exception as exc:  # one engine failing must not lose the stored reading
                db.rollback()
                logger.error("Pipeline step %s failed for reading %s: %s", step, reading.id, exc, exc_info=True)
        if was_offline:
            SensorHealthService.on_sensor_recovered(db, sensor)

    unit = sensor.storage_unit
    realtime.publish("reading", {
        "sensor_id": sensor.id, "sensor_code": sensor.sensor_code, "storage_unit_id": sensor.storage_unit_id,
        "temperature": temperature, "timestamp": msg.timestamp, "quality": quality, "simulated": simulated,
        "humidity": msg.humidity, "battery": msg.battery,
    }, facility_id=unit.facility_id if unit else None)
    INGEST_LATENCY.observe(time.perf_counter() - started)
    return IngestResult("accepted", reason, reading.id, quality)
