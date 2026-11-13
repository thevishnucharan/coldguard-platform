import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class RoutePlanRequest(BaseModel):
    incident_id: Optional[uuid.UUID] = None
    storage_unit_id: Optional[uuid.UUID] = None
    max_trip_minutes: float = Field(240, ge=30, le=720, description="Validated cold-box hold time")
    vehicle_capacity_litres: float = Field(60, ge=5, le=2000, description="Net cold-box volume per vehicle")
    vehicles: int = Field(1, ge=1, le=10)
    depart_at: Optional[datetime] = None
    allow_on_site: bool = Field(True, description="False = facility-wide problem; relocate to other facilities only")
    persist: bool = True


class RoutePlanDecision(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)


class DispatchRequest(BaseModel):
    vehicle_code: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")
    sensor_code: Optional[str] = Field(None, min_length=2, max_length=50, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    trips: Optional[List[int]] = None


class TransitReading(BaseModel):
    """One data-logger message from a vehicle in transit."""
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    temperature: Optional[float] = None          # None = logger sent no value (treated as a fault)
    sensor_status: Optional[str] = Field(None, max_length=30)   # OK | FAULT | ERROR | ...
    timestamp: Optional[datetime] = None


class DivertRequest(BaseModel):
    facility_id: uuid.UUID
    note: Optional[str] = Field(None, max_length=1000)


class NoteRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)
