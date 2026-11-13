import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import (CalibrationResult, MaintenancePriority, MaintenanceStatus, MaintenanceTrigger,
                              MaintenanceType)


class MaintenanceTicket(Base, UUIDMixin):
    __tablename__ = "maintenance_tickets"
    __table_args__ = (Index("ix_maint_status_priority", "status", "priority"),)

    ticket_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    facility_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facilities.id"), nullable=False, index=True)
    storage_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("storage_units.id"), nullable=True, index=True)
    sensor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("sensors.id"), nullable=True, index=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    maintenance_type: Mapped[MaintenanceType] = mapped_column(enum_type(MaintenanceType), default=MaintenanceType.CORRECTIVE)
    priority: Mapped[MaintenancePriority] = mapped_column(enum_type(MaintenancePriority), default=MaintenancePriority.MEDIUM)
    status: Mapped[MaintenanceStatus] = mapped_column(enum_type(MaintenanceStatus), default=MaintenanceStatus.OPEN, index=True)
    trigger: Mapped[MaintenanceTrigger] = mapped_column(enum_type(MaintenanceTrigger), default=MaintenanceTrigger.MANUAL)
    trigger_rule: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    inspection_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    repair_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_maintenance_due: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    verified_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    facility: Mapped["Facility"] = relationship()
    storage_unit: Mapped[Optional["StorageUnit"]] = relationship()
    sensor: Mapped[Optional["Sensor"]] = relationship()
    assignee: Mapped[Optional["User"]] = relationship(foreign_keys=[assigned_to])
    requester: Mapped[Optional["User"]] = relationship(foreign_keys=[requested_by])
    notes: Mapped[List["MaintenanceNote"]] = relationship(
        back_populates="ticket", order_by="MaintenanceNote.created_at", cascade="all, delete-orphan")


class MaintenanceNote(Base, UUIDMixin):
    __tablename__ = "maintenance_notes"

    ticket_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("maintenance_tickets.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), default="NOTE")  # NOTE | INSPECTION | REPAIR | EVIDENCE | STATUS
    body: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    author_name: Mapped[str] = mapped_column(String(255), default="system")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    ticket: Mapped["MaintenanceTicket"] = relationship(back_populates="notes")


class CalibrationRecord(Base, UUIDMixin):
    __tablename__ = "calibration_records"

    sensor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sensors.id"), nullable=False, index=True)
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    performed_by_name: Mapped[str] = mapped_column(String(255), default="unknown")
    calibrated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    due_date: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    result: Mapped[CalibrationResult] = mapped_column(enum_type(CalibrationResult), nullable=False)
    reference_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    measured_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    offset_applied: Mapped[float] = mapped_column(Float, default=0.0)
    certificate_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ticket_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("maintenance_tickets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    sensor: Mapped["Sensor"] = relationship()


class EquipmentEvent(Base, UUIDMixin):
    """Device/equipment history: provisioning, re-assignment, replacement, decommission."""
    __tablename__ = "equipment_events"

    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)  # SENSOR | STORAGE_UNIT
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(255), default="system")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
