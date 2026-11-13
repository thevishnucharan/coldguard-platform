import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, TimestampMixin, UUIDMixin, enum_type, utcnow
from app.models.enums import SensorStatus, StorageUnitStatus


class MonitoringPolicy(Base, UUIDMixin, TimestampMixin):
    """Approved temperature-monitoring policy. Limits are NOT hard-coded anywhere: each
    storage unit references a policy (or falls back to its own min/max)."""
    __tablename__ = "monitoring_policies"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    # readings within this margin of a limit (but still inside) => WARNING state
    warning_margin: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    # excursion lasting longer than this is CRITICAL regardless of deviation
    critical_after_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # deviation beyond limit (°C) that is CRITICAL immediately
    critical_deviation: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    expected_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    missing_telemetry_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    offline_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    approved_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class StorageUnit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "storage_units"

    unit_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_type: Mapped[str] = mapped_column(String(100), nullable=False)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[StorageUnitStatus] = mapped_column(enum_type(StorageUnitStatus), default=StorageUnitStatus.ACTIVE)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("monitoring_policies.id"), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    capacity_litres: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    installed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    last_service_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    next_service_due: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    facility: Mapped[Optional["Facility"]] = relationship(back_populates="storage_units")
    policy: Mapped[Optional["MonitoringPolicy"]] = relationship()
    sensors: Mapped[List["Sensor"]] = relationship(back_populates="storage_unit")
    batches: Mapped[List["Batch"]] = relationship(back_populates="storage_unit")
    temperature_readings: Mapped[List["TemperatureReading"]] = relationship(back_populates="storage_unit")
    violations: Mapped[List["Violation"]] = relationship(back_populates="storage_unit")

    # Effective limits: approved policy wins over unit-level legacy values
    @property
    def effective_min(self) -> float:
        return self.policy.min_temperature if self.policy else self.min_temperature

    @property
    def effective_max(self) -> float:
        return self.policy.max_temperature if self.policy else self.max_temperature


class Sensor(Base, UUIDMixin):
    __tablename__ = "sensors"

    sensor_code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    storage_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("storage_units.id"), nullable=True, index=True)
    sensor_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[SensorStatus] = mapped_column(enum_type(SensorStatus), default=SensorStatus.ONLINE)
    last_reading_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    serial_number: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    battery_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    device_key_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provisioned_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    decommissioned_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    last_calibrated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    calibration_due_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    calibration_offset: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    storage_unit: Mapped[Optional["StorageUnit"]] = relationship(back_populates="sensors")
    readings: Mapped[List["TemperatureReading"]] = relationship(back_populates="sensor")
    health_events: Mapped[List["SensorHealthEvent"]] = relationship(back_populates="sensor")
    anomalies: Mapped[List["Anomaly"]] = relationship(back_populates="sensor")
