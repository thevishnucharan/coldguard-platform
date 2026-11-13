import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SensorStatus, StorageUnitStatus


class RegionIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., min_length=2, max_length=255)
    description: Optional[str] = None


class RegionOut(RegionIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class FacilityIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Z0-9_-]+$")
    name: str = Field(..., min_length=2, max_length=255)
    facility_type: str = Field("Health Facility", max_length=60)
    region_id: uuid.UUID
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None


class FacilityUpdate(BaseModel):
    name: Optional[str] = None
    facility_type: Optional[str] = None
    region_id: Optional[uuid.UUID] = None
    address: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    is_active: Optional[bool] = None


class FacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    code: str
    name: str
    facility_type: str
    region_id: uuid.UUID
    region_name: Optional[str] = None
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    contact_name: Optional[str]
    contact_phone: Optional[str]
    is_active: bool
    created_at: datetime


class FacilitySummary(FacilityOut):
    storage_units: int = 0
    sensors_online: int = 0
    sensors_total: int = 0
    active_incidents: int = 0
    critical_incidents: int = 0
    health: str = "NORMAL"


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    description: Optional[str] = None
    min_temperature: float = Field(..., ge=-100, le=60)
    max_temperature: float = Field(..., ge=-100, le=60)
    warning_margin: float = Field(0.5, ge=0, le=10)
    critical_after_minutes: int = Field(30, ge=1, le=1440)
    critical_deviation: float = Field(3.0, gt=0, le=50)
    expected_interval_seconds: int = Field(60, ge=5, le=3600)
    missing_telemetry_minutes: int = Field(5, ge=1, le=1440)
    offline_minutes: int = Field(15, ge=1, le=2880)
    approved_by: Optional[str] = None
    reference: Optional[str] = None
    is_active: bool = True

    @model_validator(mode="after")
    def _check(self):
        if self.min_temperature >= self.max_temperature:
            raise ValueError("min_temperature must be lower than max_temperature")
        if self.offline_minutes <= self.missing_telemetry_minutes:
            raise ValueError("offline_minutes must be greater than missing_telemetry_minutes")
        return self


class PolicyOut(PolicyIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    updated_at: Optional[datetime] = None


class StorageUnitIn(BaseModel):
    unit_code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=255)
    location: str = Field(..., max_length=255)
    unit_type: str = Field(..., max_length=100)
    facility_id: uuid.UUID
    policy_id: Optional[uuid.UUID] = None
    min_temperature: Optional[float] = None
    max_temperature: Optional[float] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    capacity_litres: Optional[float] = None
    installed_at: Optional[datetime] = None
    next_service_due: Optional[datetime] = None

    @model_validator(mode="after")
    def _limits(self):
        if self.policy_id is None and (self.min_temperature is None or self.max_temperature is None):
            raise ValueError("Either policy_id or explicit min/max temperature limits are required")
        if self.min_temperature is not None and self.max_temperature is not None and self.min_temperature >= self.max_temperature:
            raise ValueError("Minimum temperature must be less than maximum temperature")
        return self


class StorageUnitUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    unit_type: Optional[str] = None
    policy_id: Optional[uuid.UUID] = None
    status: Optional[StorageUnitStatus] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    capacity_litres: Optional[float] = None
    next_service_due: Optional[datetime] = None


class StorageUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    unit_code: str
    name: str
    location: str
    unit_type: str
    status: StorageUnitStatus
    facility_id: Optional[uuid.UUID]
    policy_id: Optional[uuid.UUID]
    min_temperature: float
    max_temperature: float
    effective_min: float
    effective_max: float
    manufacturer: Optional[str]
    model: Optional[str]
    serial_number: Optional[str]
    capacity_litres: Optional[float]
    installed_at: Optional[datetime]
    last_service_at: Optional[datetime]
    next_service_due: Optional[datetime]
    created_at: datetime


class SensorProvision(BaseModel):
    sensor_code: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.:-]+$")
    storage_unit_id: uuid.UUID
    sensor_type: str = Field("Temperature", max_length=100)
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    firmware_version: Optional[str] = None
    is_simulated: bool = False
    calibration_due_at: Optional[datetime] = None


class SensorUpdate(BaseModel):
    sensor_type: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    firmware_version: Optional[str] = None
    status: Optional[SensorStatus] = None


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sensor_code: str
    storage_unit_id: Optional[uuid.UUID]
    sensor_type: str
    status: SensorStatus
    last_reading_at: Optional[datetime]
    last_temperature: Optional[float]
    serial_number: Optional[str]
    manufacturer: Optional[str]
    firmware_version: Optional[str]
    battery_level: Optional[float]
    provisioned_at: Optional[datetime]
    decommissioned_at: Optional[datetime]
    last_calibrated_at: Optional[datetime]
    calibration_due_at: Optional[datetime]
    calibration_offset: float
    is_simulated: bool
    created_at: datetime


class SensorProvisioned(SensorOut):
    device_key: str  # shown ONCE at provisioning
