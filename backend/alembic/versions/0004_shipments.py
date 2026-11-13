"""In-transit monitoring: shipments (dispatched route-plan trips) and transit alerts.

Revision ID: 0004_shipments
Revises: 0003_route_plans
Create Date: 2026-11-13

Additive only; guarded so re-running against a create_all database is safe.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004_shipments"
down_revision = "0003_route_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if not insp.has_table("shipments"):
        op.create_table(
            "shipments",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("shipment_number", sa.String(40), nullable=False),
            sa.Column("route_plan_id", sa.Uuid(), sa.ForeignKey("route_plans.id"), nullable=False),
            sa.Column("trip_no", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("facility_id", sa.Uuid(), sa.ForeignKey("facilities.id"), nullable=True),
            sa.Column("vehicle_code", sa.String(40), nullable=False),
            sa.Column("sensor_code", sa.String(60), nullable=False),
            sa.Column("cargo", sa.JSON(), nullable=False),
            sa.Column("total_doses", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("load_litres", sa.Float(), nullable=False, server_default="0"),
            sa.Column("min_temperature", sa.Float(), nullable=False),
            sa.Column("max_temperature", sa.Float(), nullable=False),
            sa.Column("hold_minutes", sa.Float(), nullable=False),
            sa.Column("sensor_state", sa.String(40), nullable=False),
            sa.Column("last_lat", sa.Float(), nullable=True),
            sa.Column("last_lon", sa.Float(), nullable=True),
            sa.Column("last_temperature", sa.Float(), nullable=True),
            sa.Column("last_reading_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("dispatched_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("dispatched_by_name", sa.String(255), nullable=False),
            sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("diverted_to_facility_id", sa.Uuid(), sa.ForeignKey("facilities.id"), nullable=True),
            sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.UniqueConstraint("route_plan_id", "trip_no", name="uq_shipment_plan_trip"),
        )
        op.create_index("ix_shipments_shipment_number", "shipments", ["shipment_number"], unique=True)
        op.create_index("ix_shipments_route_plan_id", "shipments", ["route_plan_id"])
        op.create_index("ix_shipments_facility_id", "shipments", ["facility_id"])
        op.create_index("ix_shipments_status", "shipments", ["status"])
    if not insp.has_table("transit_alerts"):
        op.create_table(
            "transit_alerts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("shipment_id", sa.Uuid(), sa.ForeignKey("shipments.id"), nullable=False),
            sa.Column("alert_type", sa.String(40), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("severity", sa.String(20), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("lat", sa.Float(), nullable=True),
            sa.Column("lon", sa.Float(), nullable=True),
            sa.Column("temperature", sa.Float(), nullable=True),
            sa.Column("minutes_in_transit", sa.Float(), nullable=False, server_default="0"),
            sa.Column("nearby", sa.JSON(), nullable=False),
            sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=True),
            sa.Column("notified_users", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("acknowledged_by_name", sa.String(255), nullable=True),
            sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_transit_alerts_shipment_status", "transit_alerts", ["shipment_id", "status"])


def downgrade() -> None:
    op.drop_table("transit_alerts")
    op.drop_table("shipments")
