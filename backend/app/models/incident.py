import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import (AlertStatus, CorrectiveActionStatus, IncidentStatus, IncidentType,
                              ViolationSeverity, ViolationStatus)


class Violation(Base, UUIDMixin):
    __tablename__ = "violations"

    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    peak_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    allowed_minimum: Mapped[float] = mapped_column(Float, nullable=False)
    allowed_maximum: Mapped[float] = mapped_column(Float, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    deviation: Mapped[float] = mapped_column(Float, nullable=False)
    violation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[ViolationSeverity] = mapped_column(enum_type(ViolationSeverity), nullable=False)
    status: Mapped[ViolationStatus] = mapped_column(enum_type(ViolationStatus), default=ViolationStatus.OPEN)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("sensors.id"), nullable=True)

    storage_unit: Mapped["StorageUnit"] = relationship(back_populates="violations")
    incident: Mapped[Optional["Incident"]] = relationship(back_populates="violation", uselist=False)


class IncidentBatch(Base):
    __tablename__ = "incident_batches"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"), primary_key=True)

    incident: Mapped["Incident"] = relationship(back_populates="batch_associations")
    batch: Mapped["Batch"] = relationship(back_populates="incident_associations")


class Incident(Base, UUIDMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_dedup", "dedup_key", "status"),
    )

    incident_number: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    violation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("violations.id"), nullable=True, unique=True)
    status: Mapped[IncidentStatus] = mapped_column(enum_type(IncidentStatus), default=IncidentStatus.OPEN, index=True)
    incident_type: Mapped[IncidentType] = mapped_column(
        enum_type(IncidentType), default=IncidentType.TEMPERATURE_EXCURSION, nullable=False)
    severity: Mapped[ViolationSeverity] = mapped_column(
        enum_type(ViolationSeverity), default=ViolationSeverity.HIGH, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="RULE", nullable=False)  # RULE | STATISTICAL | ML | MANUAL
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    storage_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("storage_units.id"), nullable=True, index=True)
    sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("sensors.id"), nullable=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    corrective_action: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    investigation_notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    escalation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    review_decision: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    closure_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vaccine_disposition: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    disposition_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    recovery_verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    violation: Mapped[Optional["Violation"]] = relationship(back_populates="incident")
    assignee: Mapped[Optional["User"]] = relationship(back_populates="assigned_incidents", foreign_keys=[assigned_to])
    reviewer: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by])
    facility: Mapped[Optional["Facility"]] = relationship()
    storage_unit: Mapped[Optional["StorageUnit"]] = relationship(foreign_keys=[storage_unit_id])
    sensor: Mapped[Optional["Sensor"]] = relationship(foreign_keys=[sensor_id])
    batch_associations: Mapped[List["IncidentBatch"]] = relationship(back_populates="incident")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="incident")
    events: Mapped[List["IncidentEvent"]] = relationship(
        back_populates="incident", order_by="IncidentEvent.created_at")
    corrective_actions: Mapped[List["CorrectiveAction"]] = relationship(
        back_populates="incident", order_by="CorrectiveAction.created_at")

    @property
    def peak_temperature(self) -> Optional[float]:
        return self.violation.peak_temperature if self.violation else None

    @property
    def excursion_start(self) -> Optional[datetime]:
        return self.violation.start_time if self.violation else self.created_at

    @property
    def excursion_end(self) -> Optional[datetime]:
        return self.violation.end_time if self.violation else None


class IncidentEvent(Base, UUIDMixin):
    """Immutable incident timeline (append-only — see app/db/immutability.py)."""
    __tablename__ = "incident_events"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)

    incident: Mapped["Incident"] = relationship(back_populates="events")


class CorrectiveAction(Base, UUIDMixin):
    __tablename__ = "corrective_actions"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(60), nullable=False, default="OPERATIONAL")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[CorrectiveActionStatus] = mapped_column(
        enum_type(CorrectiveActionStatus), default=CorrectiveActionStatus.PROPOSED, nullable=False, index=True)
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    review_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    implemented_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    implementation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    maintenance_ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("maintenance_tickets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    incident: Mapped["Incident"] = relationship(back_populates="corrective_actions")
    proposer: Mapped["User"] = relationship(foreign_keys=[proposed_by])
    reviewer: Mapped[Optional["User"]] = relationship(foreign_keys=[reviewed_by])


class Alert(Base, UUIDMixin):
    __tablename__ = "alerts"

    incident_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(100), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(enum_type(AlertStatus), default=AlertStatus.PENDING)
    sent_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    message: Mapped[str] = mapped_column(String, nullable=False)

    incident: Mapped["Incident"] = relationship(back_populates="alerts")
