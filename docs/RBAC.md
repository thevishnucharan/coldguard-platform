# Roles & Permission Matrix

Generated from `backend/app/core/permissions.py` (source of truth). ADMIN and AUDITOR have platform-wide data scope; OPERATOR/TECHNICIAN are scoped to assigned facilities; SUPERVISOR to assigned regions. Every API endpoint checks both permission and scope; out-of-scope resources return 404.

| Permission | Description | System Administrator | Facility Operator | Regional Supervisor | Maintenance Technician | Auditor / Compliance Officer |
|---|---|---|---|---|---|---|
| `platform.view` | View platform-wide health, infrastructure and global analytics | ✓ |  |  |  | ✓ |
| `platform.configure` | Change system-wide configuration, policies, escalation and integrations | ✓ |  |  |  |  |
| `simulation.control` | Start/stop demo telemetry simulation and reset demo data | ✓ |  |  |  |  |
| `regions.manage` | Create and edit regions | ✓ |  |  |  |  |
| `facilities.create` | Register facilities | ✓ |  |  |  |  |
| `facilities.view` | View facilities within scope | ✓ | ✓ | ✓ | ✓ | ✓ |
| `facilities.update` | Edit / deactivate facilities and assign staff | ✓ |  |  |  |  |
| `users.view` | List users and their activity | ✓ |  |  |  | ✓ |
| `users.create` | Create user accounts | ✓ |  |  |  |  |
| `users.update` | Update user details, activate/deactivate accounts | ✓ |  |  |  |  |
| `users.assign_roles` | Assign roles and facility/region access | ✓ |  |  |  |  |
| `devices.register` | Register, provision, re-assign and decommission IoT devices | ✓ |  |  |  |  |
| `devices.view` | View device registry and connectivity | ✓ | ✓ | ✓ | ✓ | ✓ |
| `storage.manage` | Create and edit storage units (refrigerators) | ✓ |  |  |  |  |
| `equipment.replace` | Record sensor/refrigerator replacement and update associations |  |  |  | ✓ |  |
| `telemetry.ingest` | Submit telemetry via the REST gateway | ✓ |  |  |  |  |
| `monitoring.view` | View live and historical temperature data | ✓ | ✓ | ✓ | ✓ | ✓ |
| `incidents.view` | View incidents within scope | ✓ | ✓ | ✓ | ✓ | ✓ |
| `incidents.acknowledge` | Acknowledge incidents |  | ✓ |  |  |  |
| `incidents.investigate` | Investigate incidents and add notes |  | ✓ |  |  |  |
| `incidents.escalate` | Escalate incidents |  | ✓ | ✓ |  |  |
| `incidents.review` | Supervisor review: resolve, send back or close incidents |  |  | ✓ |  |  |
| `incidents.assign` | Assign incidents to operators |  |  | ✓ |  |  |
| `corrective_actions.submit` | Propose and implement corrective actions |  | ✓ |  |  |  |
| `corrective_actions.approve` | Approve / reject corrective action proposals |  |  | ✓ |  |  |
| `inventory.view` | View vaccine products, batches and movements | ✓ | ✓ | ✓ |  | ✓ |
| `inventory.manage` | Receive, issue, adjust and transfer stock |  | ✓ |  |  |  |
| `products.manage` | Maintain the vaccine product catalogue | ✓ |  |  |  |  |
| `batches.quarantine` | Place a batch in quarantine |  | ✓ | ✓ |  |  |
| `batches.release` | Release a quarantined batch (authorised disposition) |  |  | ✓ |  |  |
| `batches.dispose` | Record disposal of a batch (authorised disposition) |  |  | ✓ |  |  |
| `maintenance.view` | View maintenance tickets | ✓ | ✓ | ✓ | ✓ | ✓ |
| `maintenance.create` | Raise maintenance requests |  | ✓ | ✓ | ✓ |  |
| `maintenance.assign` | Assign maintenance tickets to technicians |  |  | ✓ |  |  |
| `maintenance.update` | Work on tickets: accept, progress, record repairs/inspections |  |  |  | ✓ |  |
| `maintenance.verify` | Verify a repair restored operation |  | ✓ | ✓ |  |  |
| `calibration.view` | View calibration records | ✓ | ✓ | ✓ | ✓ | ✓ |
| `calibration.record` | Record sensor calibration |  |  |  | ✓ |  |
| `reports.view` | View reports and analytics | ✓ | ✓ | ✓ | ✓ | ✓ |
| `reports.export` | Export reports (CSV/PDF) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `audit.view` | View audit trails | ✓ |  | ✓ |  | ✓ |
| `notifications.view` | Receive in-app notifications | ✓ | ✓ | ✓ | ✓ | ✓ |

Separation of duties enforced in services: reviewers cannot approve their own corrective actions; technicians cannot verify their own repairs; admins hold no clinical disposition rights.
