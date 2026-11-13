"""v2 enterprise schema: regions/facilities/RBAC, incident lifecycle, inventory ledger,
maintenance & calibration, notifications, telemetry quarantine.

Revision ID: 0002_enterprise
Revises: 8bda373ce97a
Create Date: 2026-11-12

DEFENSIVE / NON-DESTRUCTIVE migration:
* Every CREATE TABLE / ADD COLUMN / CREATE INDEX is guarded, because existing deployments
  drifted from 8bda373ce97a (local DBs were built with create_all and contain tables and
  columns the first migration never created).
* PostgreSQL native enum columns are converted to VARCHAR(40) (values preserved) so new
  workflow states never need ALTER TYPE again. Legacy severities MINOR/MAJOR are mapped to
  WARNING/HIGH.
* Existing storage units, batches and incidents are back-filled into a "Legacy Facility"
  in a "Default Region" so no data is orphaned. No rows are deleted.
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0002_enterprise"
down_revision = "8bda373ce97a"
branch_labels = None
depends_on = None


def _enum(*values, **_kw):
    return sa.String(length=40)


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(name):
    return _insp().has_table(name)


def _cols(table):
    return {c["name"] for c in _insp().get_columns(table)}


def _index(table, name, cols, unique=False):
    existing = {i["name"] for i in _insp().get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, cols, unique=unique)


def _add(table, column):
    if column.name not in _cols(table):
        op.add_column(table, column)


def _is_pg():
    return op.get_bind().dialect.name == "postgresql"


ENUM_COLUMNS = [
    ("users", "role"), ("storage_units", "status"), ("sensors", "status"), ("batches", "status"),
    ("violations", "severity"), ("violations", "status"), ("incidents", "status"),
    ("alerts", "status"), ("anomalies", "severity"), ("sensor_health_events", "health_state"),
]
PG_ENUM_TYPES = ["role", "storageunitstatus", "sensorstatus", "batchstatus", "violationseverity",
                 "violationstatus", "incidentstatus", "alertstatus", "anomalyseverity", "sensorhealthstate"]


def upgrade() -> None:
    bind = op.get_bind()

    # ---------------------------------------------------------------- 1. new tables
    if not _has_table('monitoring_policies'):
      op.create_table('monitoring_policies',
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('min_temperature', sa.Float(), nullable=False),
    sa.Column('max_temperature', sa.Float(), nullable=False),
    sa.Column('warning_margin', sa.Float(), nullable=False),
    sa.Column('critical_after_minutes', sa.Integer(), nullable=False),
    sa.Column('critical_deviation', sa.Float(), nullable=False),
    sa.Column('expected_interval_seconds', sa.Integer(), nullable=False),
    sa.Column('missing_telemetry_minutes', sa.Integer(), nullable=False),
    sa.Column('offline_minutes', sa.Integer(), nullable=False),
    sa.Column('approved_by', sa.String(length=255), nullable=True),
    sa.Column('reference', sa.String(length=255), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    if not _has_table('permissions'):
      op.create_table('permissions',
    sa.Column('code', sa.String(length=80), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    if not _has_table('regions'):
      op.create_table('regions',
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    _index('regions', 'ix_regions_code', ['code'], unique=True)

    if not _has_table('roles'):
      op.create_table('roles',
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('label', sa.String(length=120), nullable=False),
    sa.Column('global_scope', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )
    if not _has_table('system_configurations'):
      op.create_table('system_configurations',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.JSON(), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    _index('system_configurations', 'ix_system_configurations_key', ['key'], unique=False)

    if not _has_table('telemetry_quarantine'):
      op.create_table('telemetry_quarantine',
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('channel', sa.String(length=30), nullable=False),
    sa.Column('sensor_code', sa.String(length=100), nullable=True),
    sa.Column('raw_payload', sa.Text(), nullable=False),
    sa.Column('reason', sa.String(length=500), nullable=False),
    sa.Column('is_simulated', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    _index('telemetry_quarantine', 'ix_telemetry_quarantine_received_at', ['received_at'], unique=False)
    _index('telemetry_quarantine', 'ix_telemetry_quarantine_sensor_code', ['sensor_code'], unique=False)

    if not _has_table('facilities'):
      op.create_table('facilities',
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('facility_type', sa.String(length=60), nullable=False),
    sa.Column('region_id', sa.Uuid(), nullable=False),
    sa.Column('address', sa.String(length=500), nullable=True),
    sa.Column('latitude', sa.Float(), nullable=True),
    sa.Column('longitude', sa.Float(), nullable=True),
    sa.Column('contact_name', sa.String(length=255), nullable=True),
    sa.Column('contact_phone', sa.String(length=50), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('facilities', 'ix_facilities_code', ['code'], unique=True)
    _index('facilities', 'ix_facilities_region_id', ['region_id'], unique=False)

    if not _has_table('notifications'):
      op.create_table('notifications',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('level', _enum('INFO', 'WARNING', 'CRITICAL', name='notificationlevel', native_enum=False, length=40), nullable=False),
    sa.Column('category', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=255), nullable=True),
    sa.Column('entity_type', sa.String(length=60), nullable=True),
    sa.Column('entity_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    _index('notifications', 'ix_notifications_created_at', ['created_at'], unique=False)
    _index('notifications', 'ix_notifications_user_read', ['user_id', 'read_at'], unique=False)

    if not _has_table('refresh_tokens'):
      op.create_table('refresh_tokens',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.String(length=128), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('user_agent', sa.String(length=255), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    _index('refresh_tokens', 'ix_refresh_tokens_family_id', ['family_id'], unique=False)
    _index('refresh_tokens', 'ix_refresh_tokens_token_hash', ['token_hash'], unique=True)
    _index('refresh_tokens', 'ix_refresh_tokens_user_id', ['user_id'], unique=False)

    if not _has_table('role_permissions'):
      op.create_table('role_permissions',
    sa.Column('role_code', sa.String(length=40), nullable=False),
    sa.Column('permission_code', sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(['permission_code'], ['permissions.code'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['role_code'], ['roles.code'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('role_code', 'permission_code')
    )
    if not _has_table('equipment_events'):
      op.create_table('equipment_events',
    sa.Column('entity_type', sa.String(length=30), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('facility_id', sa.Uuid(), nullable=True),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['facility_id'], ['facilities.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('equipment_events', 'ix_equipment_events_created_at', ['created_at'], unique=False)
    _index('equipment_events', 'ix_equipment_events_entity_id', ['entity_id'], unique=False)
    _index('equipment_events', 'ix_equipment_events_facility_id', ['facility_id'], unique=False)

    if not _has_table('user_role_assignments'):
      op.create_table('user_role_assignments',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('role', _enum('ADMIN', 'OPERATOR', 'SUPERVISOR', 'TECHNICIAN', 'AUDITOR', name='role', native_enum=False, length=40), nullable=False),
    sa.Column('facility_id', sa.Uuid(), nullable=True),
    sa.Column('region_id', sa.Uuid(), nullable=True),
    sa.Column('assigned_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['assigned_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['facility_id'], ['facilities.id'], ),
    sa.ForeignKeyConstraint(['region_id'], ['regions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'facility_id', 'region_id', name='uq_user_scope')
    )
    _index('user_role_assignments', 'ix_user_role_assignments_facility_id', ['facility_id'], unique=False)
    _index('user_role_assignments', 'ix_user_role_assignments_region_id', ['region_id'], unique=False)
    _index('user_role_assignments', 'ix_user_role_assignments_user_id', ['user_id'], unique=False)

    if not _has_table('temperature_rollups'):
      op.create_table('temperature_rollups',
    sa.Column('sensor_id', sa.Uuid(), nullable=False),
    sa.Column('storage_unit_id', sa.Uuid(), nullable=False),
    sa.Column('hour', sa.DateTime(timezone=True), nullable=False),
    sa.Column('min_temperature', sa.Float(), nullable=False),
    sa.Column('max_temperature', sa.Float(), nullable=False),
    sa.Column('avg_temperature', sa.Float(), nullable=False),
    sa.Column('reading_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ),
    sa.ForeignKeyConstraint(['storage_unit_id'], ['storage_units.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sensor_id', 'hour', name='uq_rollup_sensor_hour')
    )
    _index('temperature_rollups', 'ix_temperature_rollups_hour', ['hour'], unique=False)
    _index('temperature_rollups', 'ix_temperature_rollups_sensor_id', ['sensor_id'], unique=False)
    _index('temperature_rollups', 'ix_temperature_rollups_storage_unit_id', ['storage_unit_id'], unique=False)

    if not _has_table('incident_events'):
      op.create_table('incident_events',
    sa.Column('incident_id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('from_status', sa.String(length=40), nullable=True),
    sa.Column('to_status', sa.String(length=40), nullable=True),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_name', sa.String(length=255), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('data', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('incident_events', 'ix_incident_events_created_at', ['created_at'], unique=False)
    _index('incident_events', 'ix_incident_events_incident_id', ['incident_id'], unique=False)

    if not _has_table('inventory_movements'):
      op.create_table('inventory_movements',
    sa.Column('batch_id', sa.Uuid(), nullable=False),
    sa.Column('facility_id', sa.Uuid(), nullable=True),
    sa.Column('movement_type', _enum('RECEIPT', 'ISSUE', 'ADJUSTMENT', 'TRANSFER_OUT', 'TRANSFER_IN', 'QUARANTINE', 'RELEASE', 'DISPOSAL', 'EXPIRY', 'RECONCILIATION', name='movementtype', native_enum=False, length=40), nullable=False),
    sa.Column('quantity_change', sa.Integer(), nullable=False),
    sa.Column('quantity_after', sa.Integer(), nullable=False),
    sa.Column('from_storage_unit_id', sa.Uuid(), nullable=True),
    sa.Column('to_storage_unit_id', sa.Uuid(), nullable=True),
    sa.Column('status_before', sa.String(length=30), nullable=True),
    sa.Column('status_after', sa.String(length=30), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('reference', sa.String(length=120), nullable=True),
    sa.Column('incident_id', sa.Uuid(), nullable=True),
    sa.Column('performed_by', sa.Uuid(), nullable=True),
    sa.Column('performed_by_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], ),
    sa.ForeignKeyConstraint(['facility_id'], ['facilities.id'], ),
    sa.ForeignKeyConstraint(['from_storage_unit_id'], ['storage_units.id'], ),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
    sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['to_storage_unit_id'], ['storage_units.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('inventory_movements', 'ix_inventory_movements_batch_id', ['batch_id'], unique=False)
    _index('inventory_movements', 'ix_inventory_movements_created_at', ['created_at'], unique=False)
    _index('inventory_movements', 'ix_inventory_movements_facility_id', ['facility_id'], unique=False)
    _index('inventory_movements', 'ix_inventory_movements_movement_type', ['movement_type'], unique=False)

    if not _has_table('maintenance_tickets'):
      op.create_table('maintenance_tickets',
    sa.Column('ticket_number', sa.String(length=40), nullable=False),
    sa.Column('facility_id', sa.Uuid(), nullable=False),
    sa.Column('storage_unit_id', sa.Uuid(), nullable=True),
    sa.Column('sensor_id', sa.Uuid(), nullable=True),
    sa.Column('incident_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('maintenance_type', _enum('CORRECTIVE', 'PREVENTIVE', 'CALIBRATION', 'INSPECTION', 'REPLACEMENT', name='maintenancetype', native_enum=False, length=40), nullable=False),
    sa.Column('priority', _enum('LOW', 'MEDIUM', 'HIGH', 'URGENT', name='maintenancepriority', native_enum=False, length=40), nullable=False),
    sa.Column('status', _enum('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'VERIFIED', 'CLOSED', name='maintenancestatus', native_enum=False, length=40), nullable=False),
    sa.Column('trigger', _enum('MANUAL', 'RULE', 'ML', 'PREVENTIVE', name='maintenancetrigger', native_enum=False, length=40), nullable=False),
    sa.Column('trigger_rule', sa.String(length=120), nullable=True),
    sa.Column('dedup_key', sa.String(length=200), nullable=True),
    sa.Column('requested_by', sa.Uuid(), nullable=True),
    sa.Column('assigned_to', sa.Uuid(), nullable=True),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('inspection_results', sa.Text(), nullable=True),
    sa.Column('repair_notes', sa.Text(), nullable=True),
    sa.Column('next_maintenance_due', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_by', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], ),
    sa.ForeignKeyConstraint(['facility_id'], ['facilities.id'], ),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ),
    sa.ForeignKeyConstraint(['storage_unit_id'], ['storage_units.id'], ),
    sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('maintenance_tickets', 'ix_maint_status_priority', ['status', 'priority'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_assigned_to', ['assigned_to'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_created_at', ['created_at'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_dedup_key', ['dedup_key'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_facility_id', ['facility_id'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_sensor_id', ['sensor_id'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_status', ['status'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_storage_unit_id', ['storage_unit_id'], unique=False)
    _index('maintenance_tickets', 'ix_maintenance_tickets_ticket_number', ['ticket_number'], unique=True)

    if not _has_table('calibration_records'):
      op.create_table('calibration_records',
    sa.Column('sensor_id', sa.Uuid(), nullable=False),
    sa.Column('performed_by', sa.Uuid(), nullable=True),
    sa.Column('performed_by_name', sa.String(length=255), nullable=False),
    sa.Column('calibrated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('result', _enum('PASS', 'ADJUSTED', 'FAIL', name='calibrationresult', native_enum=False, length=40), nullable=False),
    sa.Column('reference_temperature', sa.Float(), nullable=True),
    sa.Column('measured_temperature', sa.Float(), nullable=True),
    sa.Column('offset_applied', sa.Float(), nullable=False),
    sa.Column('certificate_reference', sa.String(length=255), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('ticket_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['sensor_id'], ['sensors.id'], ),
    sa.ForeignKeyConstraint(['ticket_id'], ['maintenance_tickets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('calibration_records', 'ix_calibration_records_calibrated_at', ['calibrated_at'], unique=False)
    _index('calibration_records', 'ix_calibration_records_due_date', ['due_date'], unique=False)
    _index('calibration_records', 'ix_calibration_records_sensor_id', ['sensor_id'], unique=False)

    if not _has_table('corrective_actions'):
      op.create_table('corrective_actions',
    sa.Column('incident_id', sa.Uuid(), nullable=False),
    sa.Column('action_type', sa.String(length=60), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('root_cause', sa.Text(), nullable=True),
    sa.Column('status', _enum('PROPOSED', 'APPROVED', 'REJECTED', 'REVISION_REQUESTED', 'IMPLEMENTED', 'VERIFIED', name='correctiveactionstatus', native_enum=False, length=40), nullable=False),
    sa.Column('proposed_by', sa.Uuid(), nullable=False),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('review_comment', sa.Text(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('implemented_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('implementation_notes', sa.Text(), nullable=True),
    sa.Column('maintenance_ticket_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ),
    sa.ForeignKeyConstraint(['maintenance_ticket_id'], ['maintenance_tickets.id'], ),
    sa.ForeignKeyConstraint(['proposed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('corrective_actions', 'ix_corrective_actions_incident_id', ['incident_id'], unique=False)
    _index('corrective_actions', 'ix_corrective_actions_status', ['status'], unique=False)

    if not _has_table('maintenance_notes'):
      op.create_table('maintenance_notes',
    sa.Column('ticket_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('evidence_reference', sa.String(length=500), nullable=True),
    sa.Column('author_id', sa.Uuid(), nullable=True),
    sa.Column('author_name', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['ticket_id'], ['maintenance_tickets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    _index('maintenance_notes', 'ix_maintenance_notes_ticket_id', ['ticket_id'], unique=False)


    # ---------------------------------------------------------------- 2. native enums -> varchar
    if _is_pg():
        for table, col in ENUM_COLUMNS:
            if _has_table(table) and col in _cols(table):
                op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(40) USING {col}::text")
        for t in PG_ENUM_TYPES:
            op.execute(f"DROP TYPE IF EXISTS {t}")
    op.execute("UPDATE violations SET severity='WARNING' WHERE severity='MINOR'")
    op.execute("UPDATE violations SET severity='HIGH' WHERE severity='MAJOR'")

    # ---------------------------------------------------------------- 3. new columns
    F, S = sa.false(), sa.String
    _add("users", sa.Column("title", S(120), nullable=True))
    _add("users", sa.Column("phone", S(50), nullable=True))
    _add("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    _add("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    _add("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    _add("storage_units", sa.Column("facility_id", sa.Uuid(), nullable=True))
    _add("storage_units", sa.Column("policy_id", sa.Uuid(), nullable=True))
    for name, typ in [("manufacturer", S(120)), ("model", S(120)), ("serial_number", S(120)),
                      ("capacity_litres", sa.Float()), ("installed_at", sa.DateTime(timezone=True)),
                      ("last_service_at", sa.DateTime(timezone=True)), ("next_service_due", sa.DateTime(timezone=True))]:
        _add("storage_units", sa.Column(name, typ, nullable=True))

    for name, typ in [("serial_number", S(120)), ("manufacturer", S(120)), ("firmware_version", S(50)),
                      ("battery_level", sa.Float()), ("last_temperature", sa.Float()), ("device_key_hash", S(128)),
                      ("provisioned_at", sa.DateTime(timezone=True)), ("decommissioned_at", sa.DateTime(timezone=True)),
                      ("last_calibrated_at", sa.DateTime(timezone=True)), ("calibration_due_at", sa.DateTime(timezone=True))]:
        _add("sensors", sa.Column(name, typ, nullable=True))
    _add("sensors", sa.Column("calibration_offset", sa.Float(), nullable=False, server_default="0"))
    _add("sensors", sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=F))

    _add("products", sa.Column("manufacturer", S(255), nullable=True))
    _add("products", sa.Column("presentation", S(120), nullable=True))
    _add("products", sa.Column("doses_per_vial", sa.Integer(), nullable=True))

    _add("batches", sa.Column("facility_id", sa.Uuid(), nullable=True))
    _add("batches", sa.Column("manufacturer", S(255), nullable=True))
    _add("batches", sa.Column("manufacturing_date", sa.DateTime(timezone=True), nullable=True))
    _add("batches", sa.Column("receipt_date", sa.DateTime(timezone=True), nullable=True))
    _add("batches", sa.Column("supplier", S(255), nullable=True))
    _add("batches", sa.Column("quantity_received", sa.Integer(), nullable=False, server_default="0"))
    _add("batches", sa.Column("current_quantity", sa.Integer(), nullable=False, server_default="0"))
    _add("batches", sa.Column("unit_of_measure", S(30), nullable=False, server_default="doses"))
    _add("batches", sa.Column("quarantine_reason", sa.Text(), nullable=True))
    _add("batches", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))

    _add("temperature_readings", sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=F))
    _add("temperature_readings", sa.Column("message_id", S(100), nullable=True))
    _add("temperature_readings", sa.Column("humidity", sa.Float(), nullable=True))
    _add("temperature_readings", sa.Column("battery_level", sa.Float(), nullable=True))

    _add("sensor_health_events", sa.Column("health_state", S(40), nullable=False, server_default="WARNING"))

    for name, typ in [("storage_unit_id", sa.Uuid()), ("temperature", sa.Float()), ("model_version", S(60)),
                      ("context", sa.JSON()), ("explanation", sa.JSON()), ("incident_id", sa.Uuid())]:
        _add("anomalies", sa.Column(name, typ, nullable=True))
    _add("anomalies", sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=F))

    for name, typ in [("actor_name", S(255)), ("actor_role", S(40)), ("ip_address", S(64)), ("facility_id", sa.Uuid())]:
        _add("audit_logs", sa.Column(name, typ, nullable=True))
    _add("audit_logs", sa.Column("category", S(30), nullable=False, server_default="OPERATIONS"))
    _add("audit_logs", sa.Column("outcome", S(20), nullable=False, server_default="SUCCESS"))

    _add("violations", sa.Column("sensor_id", sa.Uuid(), nullable=True))

    _add("incidents", sa.Column("incident_type", S(40), nullable=False, server_default="TEMPERATURE_EXCURSION"))
    _add("incidents", sa.Column("severity", S(40), nullable=False, server_default="HIGH"))
    _add("incidents", sa.Column("source", S(30), nullable=False, server_default="RULE"))
    _add("incidents", sa.Column("is_simulated", sa.Boolean(), nullable=False, server_default=F))
    _add("incidents", sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="0"))
    for name, typ in [("title", S(255)), ("description", sa.Text()), ("facility_id", sa.Uuid()),
                      ("storage_unit_id", sa.Uuid()), ("sensor_id", sa.Uuid()), ("dedup_key", S(200)),
                      ("ai_summary", sa.String()), ("escalated_at", sa.DateTime(timezone=True)),
                      ("escalation_reason", S(255)), ("review_decision", S(40)), ("reviewed_by", sa.Uuid()),
                      ("reviewed_at", sa.DateTime(timezone=True)), ("review_notes", sa.Text()),
                      ("closure_evidence", sa.Text()), ("vaccine_disposition", sa.Text()),
                      ("disposition_by", sa.Uuid()), ("recovery_verified_at", sa.DateTime(timezone=True)),
                      ("acknowledged_at", sa.DateTime(timezone=True))]:
        _add("incidents", sa.Column(name, typ, nullable=True))

    # ---------------------------------------------------------------- 4. relax NOT NULLs
    for table, col in [("incidents", "violation_id"), ("sensors", "storage_unit_id"), ("audit_logs", "user_id")]:
        if _is_pg():
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL")
        else:
            with op.batch_alter_table(table) as b:
                b.alter_column(col, existing_type=sa.Uuid(), nullable=True)

    # ---------------------------------------------------------------- 5. foreign keys (PostgreSQL)
    # SQLite cannot add FK constraints without rebuilding tables and does not enforce them
    # by default; the ORM relationships still hold. PostgreSQL gets named constraints.
    if _is_pg():
        fks = [
            ("fk_units_facility", "storage_units", "facilities", "facility_id"),
            ("fk_units_policy", "storage_units", "monitoring_policies", "policy_id"),
            ("fk_batches_facility", "batches", "facilities", "facility_id"),
            ("fk_incidents_facility", "incidents", "facilities", "facility_id"),
            ("fk_incidents_unit", "incidents", "storage_units", "storage_unit_id"),
            ("fk_incidents_sensor", "incidents", "sensors", "sensor_id"),
            ("fk_incidents_reviewer", "incidents", "users", "reviewed_by"),
            ("fk_incidents_disposition", "incidents", "users", "disposition_by"),
            ("fk_anomalies_unit", "anomalies", "storage_units", "storage_unit_id"),
            ("fk_anomalies_incident", "anomalies", "incidents", "incident_id"),
            ("fk_audit_facility", "audit_logs", "facilities", "facility_id"),
            ("fk_violations_sensor", "violations", "sensors", "sensor_id"),
        ]
        existing = set()
        for t in {f[1] for f in fks}:
            for fk in _insp().get_foreign_keys(t):
                existing.add((t, tuple(fk["constrained_columns"])))
        for name, table, ref, col in fks:
            if (table, (col,)) not in existing:
                op.create_foreign_key(name, table, ref, [col], ["id"])

    # ---------------------------------------------------------------- 6. indexes
    for table, name, cols in [
        ("users", "ix_users_role", ["role"]),
        ("storage_units", "ix_storage_units_facility_id", ["facility_id"]),
        ("sensors", "ix_sensors_storage_unit_id", ["storage_unit_id"]),
        ("batches", "ix_batches_expiry", ["expiry_date"]),
        ("batches", "ix_batches_facility_status", ["facility_id", "status"]),
        ("batches", "ix_batches_product_id", ["product_id"]),
        ("batches", "ix_batches_storage_unit_id", ["storage_unit_id"]),
        ("temperature_readings", "ix_readings_sensor_ts", ["sensor_id", "timestamp"]),
        ("temperature_readings", "ix_readings_unit_ts", ["storage_unit_id", "timestamp"]),
        ("temperature_readings", "ix_temperature_readings_message_id", ["message_id"]),
        ("sensor_health_events", "ix_sensor_health_events_sensor_id", ["sensor_id"]),
        ("sensor_health_events", "ix_sensor_health_events_detected_at", ["detected_at"]),
        ("anomalies", "ix_anomalies_sensor_id", ["sensor_id"]),
        ("anomalies", "ix_anomalies_detected_at", ["detected_at"]),
        ("anomalies", "ix_anomalies_storage_unit_id", ["storage_unit_id"]),
        ("audit_logs", "ix_audit_entity", ["entity_type", "entity_id"]),
        ("audit_logs", "ix_audit_logs_action", ["action"]),
        ("audit_logs", "ix_audit_logs_category", ["category"]),
        ("audit_logs", "ix_audit_logs_user_id", ["user_id"]),
        ("audit_logs", "ix_audit_logs_facility_id", ["facility_id"]),
        ("violations", "ix_violations_storage_unit_id", ["storage_unit_id"]),
        ("incidents", "ix_incidents_status", ["status"]),
        ("incidents", "ix_incidents_created_at", ["created_at"]),
        ("incidents", "ix_incidents_facility_id", ["facility_id"]),
        ("incidents", "ix_incidents_storage_unit_id", ["storage_unit_id"]),
        ("incidents", "ix_incidents_status_severity", ["status", "severity"]),
        ("incidents", "ix_incidents_dedup", ["dedup_key", "status"]),
        ("alerts", "ix_alerts_incident_id", ["incident_id"]),
    ]:
        _index(table, name, cols)

    # ---------------------------------------------------------------- 7. data back-fill
    _backfill(bind)


def _backfill(bind):
    """Attach pre-existing assets to a Legacy Facility and derive incident fields."""
    orphan_units = bind.execute(sa.text("SELECT COUNT(*) FROM storage_units WHERE facility_id IS NULL")).scalar()
    if orphan_units:
        now = datetime.now(timezone.utc)

        def new_id():
            return uuid.uuid4().hex if bind.dialect.name == "sqlite" else str(uuid.uuid4())

        region_id = bind.execute(sa.text("SELECT id FROM regions WHERE code='DEFAULT'")).scalar()
        if not region_id:
            region_id = new_id()
            bind.execute(sa.text(
                "INSERT INTO regions (id, code, name, description, created_at, updated_at) "
                "VALUES (:id, 'DEFAULT', 'Default Region', 'Created by migration 0002 for legacy data', :n, :n)"),
                {"id": region_id, "n": now})
        fac_id = bind.execute(sa.text("SELECT id FROM facilities WHERE code='LEGACY'")).scalar()
        if not fac_id:
            fac_id = new_id()
            bind.execute(sa.text(
                "INSERT INTO facilities (id, code, name, facility_type, region_id, is_active, created_at, updated_at) "
                "VALUES (:id, 'LEGACY', 'Legacy Facility', 'Migrated', :r, :t, :n, :n)"),
                {"id": fac_id, "r": region_id, "t": True, "n": now})
        bind.execute(sa.text("UPDATE storage_units SET facility_id=:f WHERE facility_id IS NULL"), {"f": fac_id})

    bind.execute(sa.text(
        "UPDATE batches SET facility_id = (SELECT su.facility_id FROM storage_units su "
        "WHERE su.id = batches.storage_unit_id) WHERE facility_id IS NULL"))
    bind.execute(sa.text("UPDATE batches SET receipt_date = start_time WHERE receipt_date IS NULL"))
    bind.execute(sa.text("UPDATE batches SET status='DEPLETED' WHERE status='COMPLETED'"))
    bind.execute(sa.text(
        "UPDATE incidents SET storage_unit_id = (SELECT v.storage_unit_id FROM violations v "
        "WHERE v.id = incidents.violation_id) WHERE storage_unit_id IS NULL AND violation_id IS NOT NULL"))
    bind.execute(sa.text(
        "UPDATE incidents SET severity = (SELECT v.severity FROM violations v "
        "WHERE v.id = incidents.violation_id) WHERE violation_id IS NOT NULL"))
    bind.execute(sa.text(
        "UPDATE incidents SET facility_id = (SELECT su.facility_id FROM storage_units su "
        "WHERE su.id = incidents.storage_unit_id) WHERE facility_id IS NULL"))
    bind.execute(sa.text("UPDATE incidents SET title = 'Temperature excursion (migrated)' WHERE title IS NULL"))


def downgrade() -> None:
    # Data-preserving policy: v2 tables hold ledgers and audit records that must not be lost
    # by an automatic downgrade. Restore from a pre-upgrade backup instead (docs/DEPLOYMENT.md).
    raise RuntimeError("Downgrade of 0002_enterprise is intentionally unsupported; restore from backup.")
