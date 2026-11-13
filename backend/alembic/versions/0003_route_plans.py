"""Excursion relocation route plans (ML-assisted logistics).

Revision ID: 0003_route_plans
Revises: 0002_enterprise
Create Date: 2026-11-13

Additive only: one new table, guarded so re-running against a create_all database is safe.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_route_plans"
down_revision = "0002_enterprise"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if insp.has_table("route_plans"):
        return
    op.create_table(
        "route_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_number", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("source_storage_unit_id", sa.Uuid(), sa.ForeignKey("storage_units.id"), nullable=False),
        sa.Column("facility_id", sa.Uuid(), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("total_doses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unassigned_doses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trip_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("exposure_dose_minutes", sa.Float(), nullable=False, server_default="0"),
        sa.Column("baseline_exposure_dose_minutes", sa.Float(), nullable=True),
        sa.Column("improvement_pct", sa.Float(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_by_name", sa.String(255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_route_plans_plan_number", "route_plans", ["plan_number"], unique=True)
    op.create_index("ix_route_plans_incident_id", "route_plans", ["incident_id"])
    op.create_index("ix_route_plans_facility_id", "route_plans", ["facility_id"])
    op.create_index("ix_route_plans_status_created", "route_plans", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("route_plans")
