"""
Centralised permission matrix.

Every authorization decision in the API goes through a *permission* string, never a role
name. Roles are bundles of permissions defined here; the matrix is also persisted to the
`roles` / `permissions` / `role_permissions` tables (see `services/rbac.py`) so it can be
inspected by auditors and the admin UI, but this module is the source of truth.

Data scope (which facilities a user may see) is a separate concern handled by
`app/services/access.py`.
"""
from __future__ import annotations

from typing import Dict, FrozenSet

from app.models.enums import Role

# permission -> human description
PERMISSIONS: Dict[str, str] = {
    # platform
    "platform.view": "View platform-wide health, infrastructure and global analytics",
    "platform.configure": "Change system-wide configuration, policies, escalation and integrations",
    "simulation.control": "Start/stop demo telemetry simulation and reset demo data",
    # organisation
    "regions.manage": "Create and edit regions",
    "facilities.create": "Register facilities",
    "facilities.view": "View facilities within scope",
    "facilities.update": "Edit / deactivate facilities and assign staff",
    # users
    "users.view": "List users and their activity",
    "users.create": "Create user accounts",
    "users.update": "Update user details, activate/deactivate accounts",
    "users.assign_roles": "Assign roles and facility/region access",
    # devices & equipment
    "devices.register": "Register, provision, re-assign and decommission IoT devices",
    "devices.view": "View device registry and connectivity",
    "storage.manage": "Create and edit storage units (refrigerators)",
    "equipment.replace": "Record sensor/refrigerator replacement and update associations",
    # telemetry / monitoring
    "telemetry.ingest": "Submit telemetry via the REST gateway",
    "monitoring.view": "View live and historical temperature data",
    # incidents
    "incidents.view": "View incidents within scope",
    "incidents.acknowledge": "Acknowledge incidents",
    "incidents.investigate": "Investigate incidents and add notes",
    "incidents.escalate": "Escalate incidents",
    "incidents.review": "Supervisor review: resolve, send back or close incidents",
    "incidents.assign": "Assign incidents to operators",
    "corrective_actions.submit": "Propose and implement corrective actions",
    "corrective_actions.approve": "Approve / reject corrective action proposals",
    # inventory
    "inventory.view": "View vaccine products, batches and movements",
    "inventory.manage": "Receive, issue, adjust and transfer stock",
    "products.manage": "Maintain the vaccine product catalogue",
    "batches.quarantine": "Place a batch in quarantine",
    "batches.release": "Release a quarantined batch (authorised disposition)",
    "batches.dispose": "Record disposal of a batch (authorised disposition)",
    # maintenance
    "maintenance.view": "View maintenance tickets",
    "maintenance.create": "Raise maintenance requests",
    "maintenance.assign": "Assign maintenance tickets to technicians",
    "maintenance.update": "Work on tickets: accept, progress, record repairs/inspections",
    "maintenance.verify": "Verify a repair restored operation",
    "calibration.view": "View calibration records",
    "calibration.record": "Record sensor calibration",
    # reports & audit
    "reports.view": "View reports and analytics",
    "reports.export": "Export reports (CSV/PDF)",
    "audit.view": "View audit trails",
    "notifications.view": "Receive in-app notifications",
}

_ALL = frozenset(PERMISSIONS)

ROLE_PERMISSIONS: Dict[Role, FrozenSet[str]] = {
    # Administrator: platform & infrastructure. Deliberately NO incident acknowledgement,
    # stock management, maintenance work or batch disposition.
    Role.ADMIN: frozenset({
        "platform.view", "platform.configure", "simulation.control",
        "regions.manage", "facilities.create", "facilities.view", "facilities.update",
        "users.view", "users.create", "users.update", "users.assign_roles",
        "devices.register", "devices.view", "storage.manage", "telemetry.ingest",
        "monitoring.view", "incidents.view", "inventory.view", "products.manage",
        "maintenance.view", "calibration.view",
        "reports.view", "reports.export", "audit.view", "notifications.view",
    }),
    # Facility operator: day-to-day operations at assigned facilities.
    Role.OPERATOR: frozenset({
        "facilities.view", "devices.view", "monitoring.view",
        "incidents.view", "incidents.acknowledge", "incidents.investigate", "incidents.escalate",
        "corrective_actions.submit",
        "inventory.view", "inventory.manage", "batches.quarantine",
        "maintenance.view", "maintenance.create", "maintenance.verify", "calibration.view",
        "reports.view", "reports.export", "notifications.view",
    }),
    # Regional supervisor: oversight + approvals + disposition for their region.
    Role.SUPERVISOR: frozenset({
        "facilities.view", "devices.view", "monitoring.view",
        "incidents.view", "incidents.escalate", "incidents.review", "incidents.assign",
        "corrective_actions.approve",
        "inventory.view", "batches.quarantine", "batches.release", "batches.dispose",
        "maintenance.view", "maintenance.create", "maintenance.assign", "maintenance.verify",
        "calibration.view",
        "reports.view", "reports.export", "audit.view", "notifications.view",
    }),
    # Technician: equipment only. No stock, no disposition.
    Role.TECHNICIAN: frozenset({
        "facilities.view", "devices.view", "monitoring.view", "incidents.view",
        "equipment.replace",
        "maintenance.view", "maintenance.create", "maintenance.update",
        "calibration.view", "calibration.record",
        "reports.view", "reports.export", "notifications.view",
    }),
    # Auditor: read-only everything (global scope), can export.
    Role.AUDITOR: frozenset({
        "platform.view", "facilities.view", "devices.view", "monitoring.view", "incidents.view",
        "inventory.view", "maintenance.view", "calibration.view", "users.view",
        "reports.view", "reports.export", "audit.view", "notifications.view",
    }),
}

# Roles whose data scope is platform-wide (not facility/region restricted)
GLOBAL_SCOPE_ROLES = frozenset({Role.ADMIN, Role.AUDITOR})

ROLE_LABELS = {
    Role.ADMIN: "System Administrator",
    Role.OPERATOR: "Facility Operator",
    Role.SUPERVISOR: "Regional Supervisor",
    Role.TECHNICIAN: "Maintenance Technician",
    Role.AUDITOR: "Auditor / Compliance Officer",
}


def permissions_for_role(role: Role | str) -> FrozenSet[str]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except (ValueError, KeyError):
        return frozenset()


def role_has(role: Role | str, permission: str) -> bool:
    if permission not in _ALL:
        raise KeyError(f"Unknown permission '{permission}'")
    return permission in permissions_for_role(role)
