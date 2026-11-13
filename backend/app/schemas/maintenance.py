import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (CalibrationResult, MaintenancePriority, MaintenanceStatus, MaintenanceTrigger,
                              MaintenanceType)


class TicketIn(BaseModel):
    facility_id: uuid.UUID
    storage_unit_id: Optional[uuid.UUID] = None
    sensor_id: Optional[uuid.UUID] = None
    incident_id: Optional[uuid.UUID] = None
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=5, max_length=4000)
    priority: MaintenancePriority = MaintenancePriority.MEDIUM
    maintenance_type: MaintenanceType = MaintenanceType.CORRECTIVE
    due_date: Optional[datetime] = None


class AssignIn(BaseModel):
    technician_id: uuid.UUID


class NoteIn(BaseModel):
    body: str = Field(..., min_length=2, max_length=4000)
    kind: str = Field("NOTE", pattern="^(NOTE|INSPECTION|REPAIR|EVIDENCE)$")
    evidence_reference: Optional[str] = Field(None, max_length=500)


class ResolveIn(BaseModel):
    repair_notes: str = Field(..., min_length=5, max_length=4000)
    next_maintenance_due: Optional[datetime] = None


class VerifyIn(BaseModel):
    ok: bool = True
    notes: Optional[str] = Field(None, max_length=4000)


class CloseIn(BaseModel):
    notes: Optional[str] = Field(None, max_length=4000)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    kind: str
    body: str
    evidence_reference: Optional[str]
    author_name: str
    created_at: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    ticket_number: str
    facility_id: uuid.UUID
    facility_name: Optional[str] = None
    storage_unit_id: Optional[uuid.UUID]
    storage_unit_code: Optional[str] = None
    sensor_id: Optional[uuid.UUID]
    sensor_code: Optional[str] = None
    incident_id: Optional[uuid.UUID]
    title: str
    description: str
    maintenance_type: MaintenanceType
    priority: MaintenancePriority
    status: MaintenanceStatus
    trigger: MaintenanceTrigger
    trigger_rule: Optional[str]
    assigned_to: Optional[uuid.UUID]
    assignee_name: Optional[str] = None
    requested_by: Optional[uuid.UUID]
    due_date: Optional[datetime]
    inspection_results: Optional[str]
    repair_notes: Optional[str]
    next_maintenance_due: Optional[datetime]
    created_at: datetime
    assigned_at: Optional[datetime]
    started_at: Optional[datetime]
    resolved_at: Optional[datetime]
    verified_at: Optional[datetime]
    closed_at: Optional[datetime]
    is_overdue: bool = False


class TicketDetail(TicketOut):
    notes: List[NoteOut] = []


class CalibrationIn(BaseModel):
    sensor_id: uuid.UUID
    calibrated_at: datetime
    result: CalibrationResult
    interval_days: int = Field(365, ge=7, le=1095)
    reference_temperature: Optional[float] = None
    measured_temperature: Optional[float] = None
    offset_applied: float = Field(0.0, ge=-10, le=10)
    certificate_reference: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=4000)
    ticket_id: Optional[uuid.UUID] = None


class CalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sensor_id: uuid.UUID
    sensor_code: Optional[str] = None
    performed_by_name: str
    calibrated_at: datetime
    due_date: datetime
    result: CalibrationResult
    reference_temperature: Optional[float]
    measured_temperature: Optional[float]
    offset_applied: float
    certificate_reference: Optional[str]
    notes: Optional[str]
    ticket_id: Optional[uuid.UUID]


class SensorReplaceIn(BaseModel):
    old_sensor_id: uuid.UUID
    new_sensor_code: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.:-]+$")
    serial_number: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=1000)
    ticket_id: Optional[uuid.UUID] = None


class UnitReplaceIn(BaseModel):
    old_storage_unit_id: uuid.UUID
    new_unit_code: str = Field(..., min_length=2, max_length=50)
    name: str = Field(..., min_length=2, max_length=255)
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    reason: str = Field(..., min_length=3, max_length=1000)


class EquipmentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    event_type: str
    details: Optional[dict]
    actor_name: str
    created_at: datetime
