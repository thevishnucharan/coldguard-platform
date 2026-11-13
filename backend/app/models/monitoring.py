import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import AnomalySeverity, SensorHealthState


class TemperatureReading(Base, UUIDMixin):
    __tablename__ = "temperature_readings"
    __table_args__ = (
        Index("ix_readings_sensor_ts", "sensor_id", "timestamp"),
        Index("ix_readings_unit_ts", "storage_unit_id", "timestamp"),
    )

    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), nullable=False, index=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    message_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    battery_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    storage_unit: Mapped["StorageUnit"] = relationship(back_populates="temperature_readings")
    sensor: Mapped["Sensor"] = relationship(back_populates="readings")
    anomaly: Mapped[Optional["Anomaly"]] = relationship(back_populates="temperature_reading", uselist=False)


class TemperatureRollup(Base, UUIDMixin):
    """Hourly aggregates kept after raw telemetry passes the retention window."""
    __tablename__ = "temperature_rollups"
    __table_args__ = (UniqueConstraint("sensor_id", "hour", name="uq_rollup_sensor_hour"),)

    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), nullable=False, index=True)
    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    hour: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    avg_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    reading_count: Mapped[int] = mapped_column(Integer, nullable=False)


class TelemetryQuarantine(Base, UUIDMixin):
    """Malformed / rejected telemetry is kept (never silently dropped) for review."""
    __tablename__ = "telemetry_quarantine"

    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)  # mqtt | rest | simulator
    sensor_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SensorHealthEvent(Base, UUIDMixin):
    __tablename__ = "sensor_health_events"

    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    health_state: Mapped[SensorHealthState] = mapped_column(enum_type(SensorHealthState), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)

    sensor: Mapped["Sensor"] = relationship(back_populates="health_events")


class Anomaly(Base, UUIDMixin):
    """Decision-support signal from statistical / ML detectors. NOT a confirmed excursion."""
    __tablename__ = "anomalies"

    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), nullable=False, index=True)
    temperature_reading_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("temperature_readings.id"), nullable=False, unique=True)
    anomaly_score: Mapped[float] = mapped_column(Float, nullable=False)
    detection_method: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[AnomalySeverity] = mapped_column(enum_type(AnomalySeverity), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    storage_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("storage_units.id"), nullable=True, index=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    sensor: Mapped["Sensor"] = relationship(back_populates="anomalies")
    temperature_reading: Mapped["TemperatureReading"] = relationship(back_populates="anomaly")
