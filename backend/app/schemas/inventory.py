import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import BatchStatus, MovementType


class ProductIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    category: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    min_temperature: float = Field(..., ge=-100, le=60)
    max_temperature: float = Field(..., ge=-100, le=60)
    manufacturer: Optional[str] = None
    presentation: Optional[str] = None
    doses_per_vial: Optional[int] = Field(None, ge=1, le=100)

    @model_validator(mode="after")
    def _check(self):
        if self.min_temperature >= self.max_temperature:
            raise ValueError("Minimum temperature must be less than maximum temperature")
        return self


class ProductOut(ProductIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime


class ReceiveIn(BaseModel):
    batch_number: str = Field(..., min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_./-]+$")
    product_id: uuid.UUID
    storage_unit_id: uuid.UUID
    quantity: int = Field(..., gt=0, le=10_000_000)
    expiry_date: datetime
    manufacturing_date: Optional[datetime] = None
    supplier: Optional[str] = Field(None, max_length=255)
    manufacturer: Optional[str] = Field(None, max_length=255)
    reference: Optional[str] = Field(None, max_length=120)


class QuantityIn(BaseModel):
    quantity: int = Field(..., gt=0, le=10_000_000)
    reason: Optional[str] = Field(None, max_length=1000)
    reference: Optional[str] = Field(None, max_length=120)
    override_fefo_reason: Optional[str] = Field(None, max_length=1000)


class AdjustIn(BaseModel):
    change: int = Field(..., ge=-10_000_000, le=10_000_000)
    reason: str = Field(..., min_length=3, max_length=1000)


class ReconcileIn(BaseModel):
    counted_quantity: int = Field(..., ge=0, le=10_000_000)
    reason: Optional[str] = Field(None, max_length=1000)


class TransferIn(BaseModel):
    to_storage_unit_id: uuid.UUID
    reason: Optional[str] = Field(None, max_length=1000)


class DispositionIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=2000)
    incident_id: Optional[uuid.UUID] = None


class FefoIssueIn(BaseModel):
    product_id: uuid.UUID
    facility_id: uuid.UUID
    quantity: int = Field(..., gt=0, le=10_000_000)
    reason: Optional[str] = Field(None, max_length=1000)
    reference: Optional[str] = Field(None, max_length=120)


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    batch_id: uuid.UUID
    batch_number: Optional[str] = None
    facility_id: Optional[uuid.UUID]
    movement_type: MovementType
    quantity_change: int
    quantity_after: int
    from_storage_unit_id: Optional[uuid.UUID]
    to_storage_unit_id: Optional[uuid.UUID]
    status_before: Optional[str]
    status_after: Optional[str]
    reason: Optional[str]
    reference: Optional[str]
    incident_id: Optional[uuid.UUID]
    performed_by_name: str
    created_at: datetime


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    batch_number: str
    product_id: uuid.UUID
    product_name: Optional[str] = None
    storage_unit_id: uuid.UUID
    storage_unit_code: Optional[str] = None
    facility_id: Optional[uuid.UUID]
    facility_name: Optional[str] = None
    status: BatchStatus
    manufacturer: Optional[str]
    manufacturing_date: Optional[datetime]
    expiry_date: datetime
    receipt_date: Optional[datetime]
    supplier: Optional[str]
    quantity_received: int
    current_quantity: int
    unit_of_measure: str
    quarantine_reason: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    expiry_bucket: Optional[str] = None
    days_to_expiry: Optional[int] = None
    excursion_count: int = 0


class BatchDetail(BatchOut):
    movements: List[MovementOut] = []
    incidents: List[dict] = []
