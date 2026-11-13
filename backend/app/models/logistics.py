import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import (RoutePlanStatus, ShipmentStatus, TransitAlertStatus, TransitAlertType,
                              TransitSensorState)


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


class Shipment(Base, UUIDMixin):
    """One dispatched vehicle trip of an APPROVED route plan. The vehicle data logger reports
    position and cargo temperature; failures raise TransitAlerts that point the driver and the
    operators to the nearest compatible cold-chain store."""
    __tablename__ = "shipments"
    __table_args__ = (UniqueConstraint("route_plan_id", "trip_no", name="uq_shipment_plan_trip"),
                      Index("ix_shipments_status", "status"))

    shipment_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    route_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("route_plans.id"), nullable=False, index=True)
    trip_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(enum_type(ShipmentStatus), default=ShipmentStatus.IN_TRANSIT,
                                                   nullable=False)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    vehicle_code: Mapped[str] = mapped_column(String(40), nullable=False)
    sensor_code: Mapped[str] = mapped_column(String(60), nullable=False)
    cargo: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)  # the plan trip (stops, batches)
    total_doses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    load_litres: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    min_temperature: Mapped[float] = mapped_column(Float, nullable=False)  # strictest range across the cargo
    max_temperature: Mapped[float] = mapped_column(Float, nullable=False)
    hold_minutes: Mapped[float] = mapped_column(Float, nullable=False)      # validated cold-box hold time
    sensor_state: Mapped[TransitSensorState] = mapped_column(enum_type(TransitSensorState),
                                                             default=TransitSensorState.OK, nullable=False)
    last_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_reading_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    dispatched_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    dispatched_by_name: Mapped[str] = mapped_column(String(255), default="system", nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    diverted_to_facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    route_plan: Mapped["RoutePlan"] = relationship()
    facility: Mapped[Optional["Facility"]] = relationship(foreign_keys=[facility_id])
    diverted_to: Mapped[Optional["Facility"]] = relationship(foreign_keys=[diverted_to_facility_id])
    alerts: Mapped[List["TransitAlert"]] = relationship(back_populates="shipment", order_by="TransitAlert.created_at")


class TransitAlert(Base, UUIDMixin):
    """An in-transit problem (logger fault, logger silence, cargo temperature excursion) with
    the nearest compatible cold-chain stores ranked by ML-predicted ETA at alert time."""
    __tablename__ = "transit_alerts"
    __table_args__ = (Index("ix_transit_alerts_shipment_status", "shipment_id", "status"),)

    shipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shipments.id"), nullable=False)
    alert_type: Mapped[TransitAlertType] = mapped_column(enum_type(TransitAlertType), nullable=False)
    status: Mapped[TransitAlertStatus] = mapped_column(enum_type(TransitAlertStatus), default=TransitAlertStatus.OPEN,
                                                       nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    minutes_in_transit: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    nearby: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    notified_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    acknowledged_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    shipment: Mapped["Shipment"] = relationship(back_populates="alerts")
    incident: Mapped[Optional["Incident"]] = relationship()
