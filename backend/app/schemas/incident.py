import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import CorrectiveActionStatus, IncidentStatus, IncidentType, ViolationSeverity


class IncidentActionRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=4000)
    assignee_id: Optional[uuid.UUID] = None
    closure_evidence: Optional[str] = Field(None, max_length=4000)
    vaccine_disposition: Optional[str] = Field(None, max_length=4000)
    false_alarm: bool = False


class NoteRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=4000)


class EscalateRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=255)


class CorrectiveActionIn(BaseModel):
    description: str = Field(..., min_length=5, max_length=4000)
    root_cause: Optional[str] = Field(None, max_length=4000)
    action_type: str = Field("OPERATIONAL", max_length=60)
    due_date: Optional[datetime] = None


class CorrectiveActionReview(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|request_revision)$")
    comment: Optional[str] = Field(None, max_length=4000)


class CorrectiveActionImplement(BaseModel):
    notes: Optional[str] = Field(None, max_length=4000)
    maintenance_ticket_id: Optional[uuid.UUID] = None


class ReviewRequest(BaseModel):
    decision: str = Field(..., pattern="^(resolve|request_more_investigation)$")
    notes: Optional[str] = Field(None, max_length=4000)


class VerifyRecoveryRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=4000)


class CorrectiveActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    incident_id: uuid.UUID
    action_type: str
    description: str
    root_cause: Optional[str]
    status: CorrectiveActionStatus
    proposed_by: uuid.UUID
    proposer_name: Optional[str] = None
    reviewed_by: Optional[uuid.UUID]
    reviewer_name: Optional[str] = None
    review_comment: Optional[str]
    reviewed_at: Optional[datetime]
    due_date: Optional[datetime]
    implemented_at: Optional[datetime]
    implementation_notes: Optional[str]
    maintenance_ticket_id: Optional[uuid.UUID]
    created_at: datetime


class IncidentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    from_status: Optional[str]
    to_status: Optional[str]
    actor_id: Optional[uuid.UUID]
    actor_name: str
    note: Optional[str]
    data: Optional[Dict[str, Any]]
    created_at: datetime


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    incident_number: str
    incident_type: IncidentType
    severity: ViolationSeverity
    status: IncidentStatus
    title: Optional[str]
    description: Optional[str]
    source: str
    is_simulated: bool
    facility_id: Optional[uuid.UUID]
    facility_name: Optional[str] = None
    storage_unit_id: Optional[uuid.UUID]
    storage_unit_code: Optional[str] = None
    sensor_id: Optional[uuid.UUID]
    sensor_code: Optional[str] = None
    violation_id: Optional[uuid.UUID]
    assigned_to: Optional[uuid.UUID]
    assignee_name: Optional[str] = None
    root_cause: Optional[str]
    corrective_action: Optional[str]
    investigation_notes: Optional[str]
    ai_summary: Optional[str]
    escalation_level: int
    escalated_at: Optional[datetime]
    escalation_reason: Optional[str]
    review_decision: Optional[str]
    reviewed_at: Optional[datetime]
    review_notes: Optional[str]
    closure_evidence: Optional[str]
    vaccine_disposition: Optional[str]
    recovery_verified_at: Optional[datetime]
    peak_temperature: Optional[float]
    excursion_start: Optional[datetime]
    excursion_end: Optional[datetime]
    created_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    closed_at: Optional[datetime]
    duration_seconds: Optional[int] = None
    limit_min: Optional[float] = None
    limit_max: Optional[float] = None


class IncidentDetail(IncidentResponse):
    events: List[IncidentEventOut] = []
    corrective_actions: List[CorrectiveActionOut] = []
    affected_batch_count: int = 0
    available_actions: List[str] = []


class ManualIncidentIn(BaseModel):
    storage_unit_id: uuid.UUID
    incident_type: IncidentType = IncidentType.EQUIPMENT_FAILURE
    severity: ViolationSeverity = ViolationSeverity.HIGH
    title: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=5, max_length=4000)


class AffectedBatchResponse(BaseModel):
    batch_id: uuid.UUID
    batch_number: str
    product_name: str
    storage_unit_code: str
    status: str
    current_quantity: int
    expiry_date: datetime
    excursion_start: datetime
    excursion_end: Optional[datetime]
    message: str
