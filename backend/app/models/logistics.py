import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import RoutePlanStatus


class RoutePlan(Base, UUIDMixin):
    """ML-assisted relocation plan for stock in a storage unit with a temperature excursion.

    DECISION SUPPORT: a plan never moves stock. Approval records an authorised decision and
    notifies the facilities involved; the actual moves are still made through the inventory
    ledger (InventoryService.transfer) by people with `inventory.manage`."""
    __tablename__ = "route_plans"
    __table_args__ = (Index("ix_route_plans_status_created", "status", "created_at"),)

    plan_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    status: Mapped[RoutePlanStatus] = mapped_column(enum_type(RoutePlanStatus), default=RoutePlanStatus.PROPOSED,
                                                    nullable=False)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id"), nullable=True, index=True)
    source_storage_unit_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("storage_units.id"), nullable=False)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    total_doses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unassigned_doses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trip_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exposure_dose_minutes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    baseline_exposure_dose_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    improvement_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    parameters: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    plan: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by_name: Mapped[str] = mapped_column(String(255), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    decided_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    incident: Mapped[Optional["Incident"]] = relationship()
    source_storage_unit: Mapped["StorageUnit"] = relationship()
    facility: Mapped[Optional["Facility"]] = relationship()
