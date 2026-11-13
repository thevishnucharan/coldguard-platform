import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RoutePlanRequest(BaseModel):
    incident_id: Optional[uuid.UUID] = None
    storage_unit_id: Optional[uuid.UUID] = None
    max_trip_minutes: float = Field(240, ge=30, le=720, description="Validated cold-box hold time")
    vehicle_capacity_litres: float = Field(60, ge=5, le=2000, description="Net cold-box volume per vehicle")
    vehicles: int = Field(1, ge=1, le=10)
    depart_at: Optional[datetime] = None
    persist: bool = True


class RoutePlanDecision(BaseModel):
    note: Optional[str] = Field(None, max_length=1000)
