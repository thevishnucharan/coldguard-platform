import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import BatchStatus, MovementType


class Product(Base, UUIDMixin):
    """Vaccine product (catalogue entry)."""
    __tablename__ = "products"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    presentation: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    doses_per_vial: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    batches: Mapped[List["Batch"]] = relationship(back_populates="product")


class Batch(Base, UUIDMixin):
    """Vaccine batch / lot with quantity tracking. Quantities only change through
    InventoryService which writes an immutable InventoryMovement for every change."""
    __tablename__ = "batches"
    __table_args__ = (
        Index("ix_batches_expiry", "expiry_date"),
        Index("ix_batches_facility_status", "facility_id", "status"),
    )

    batch_number: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)  # placed in unit
    end_time: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)  # left unit
    expiry_date: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    status: Mapped[BatchStatus] = mapped_column(enum_type(BatchStatus), default=BatchStatus.ACTIVE)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manufacturing_date: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    receipt_date: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    supplier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quantity_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(30), default="doses", nullable=False)
    quarantine_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="batches")
    storage_unit: Mapped["StorageUnit"] = relationship(back_populates="batches")
    facility: Mapped[Optional["Facility"]] = relationship()
    incident_associations: Mapped[List["IncidentBatch"]] = relationship(back_populates="batch")
    movements: Mapped[List["InventoryMovement"]] = relationship(
        back_populates="batch", order_by="InventoryMovement.created_at")


class InventoryMovement(Base, UUIDMixin):
    """Append-only stock ledger. Never updated or deleted."""
    __tablename__ = "inventory_movements"

    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    movement_type: Mapped[MovementType] = mapped_column(enum_type(MovementType), nullable=False, index=True)
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    from_storage_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("storage_units.id"), nullable=True)
    to_storage_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("storage_units.id"), nullable=True)
    status_before: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    performed_by_name: Mapped[str] = mapped_column(String(255), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)

    batch: Mapped["Batch"] = relationship(back_populates="movements")
