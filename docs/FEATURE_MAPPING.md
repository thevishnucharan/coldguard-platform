# ColdGuard — Feature Mapping (original → redesigned)

Every feature found during the audit (`EXISTING_ARCHITECTURE.md`) and where it lives after the redesign.
"Preserved" means the original logic is kept (possibly extended), not rewritten.

## Backend

| Original feature | Original location | Redesigned equivalent | Status |
|---|---|---|---|
| JWT login | `api/auth.py` `/auth/login` | Same path; adds refresh tokens, lockout, `sub`=user id, role re-read from DB every request | Extended |
| Public registration | `/auth/register` | **Removed** (security). Users are created by admins via `/users` | Removed (justified: privilege escalation) |
| `/auth/me` | `api/auth.py` | Same; now returns roles, permissions and facility scope | Extended |
| `RequireRole` | `api/deps.py` | `require_permission(...)` + `AccessScope` (facility/region filtering). `RequireRole` kept as thin wrapper for compatibility | Replaced |
| User CRUD | `api/users.py` | `/users` + role/facility assignments, activate/deactivate, activity view | Extended |
| System configurations | `/configurations` | Same + monitoring policies (`/policies`) and escalation/notification settings | Extended |
| Storage units CRUD | `/storage-units` | Same path; units belong to a facility, link to a monitoring policy, equipment metadata | Extended |
| Sensors CRUD + health | `/sensors`, `/sensors/health` | Device registry: provisioning, decommission, battery, firmware, calibration due, simulated flag | Extended |
| Products / batches CRUD | `/products`, `/batches` | Vaccine products + batch traceability, quantities, FEFO, quarantine/release, movements (`/inventory/*`) | Extended |
| REST telemetry ingest | `/temperature/readings(/bulk)` | Kept, now authenticated with an ingest key (gateway) or JWT with `telemetry.ingest`; every reading validated individually | Extended |
| Local/Azure event queue | `adapters/events.py` | Preserved; MQTT added as the primary device channel | Preserved + MQTT |
| DataQualityEngine | `engines/quality.py` | Preserved; rejected readings now stored in `telemetry_quarantine` | Preserved |
| ViolationEngine | `engines/violation.py` | Preserved; uses monitoring policy limits, opens typed incidents, dedups | Preserved |
| SeverityEngine | `engines/severity.py` | Preserved unchanged | Preserved |
| Sensor health engine | `services/sensor_health.py` | Preserved; offline sweep moved to worker; offline/missing-telemetry incidents | Preserved |
| Incident lifecycle | `services/incident.py` | DETECTED→OPEN→ACKNOWLEDGED→INVESTIGATING→CORRECTIVE_ACTION_PENDING→UNDER_REVIEW→RESOLVED→CLOSED, `incident_events`, corrective actions, supervisor review | Extended |
| Affected batch identification | `IncidentService.identify_affected_batches` | Preserved; now read-only for auditors, also auto-run on incident creation | Preserved |
| Alerts | `services/alert.py` | Preserved (`alerts` table) + in-app `notifications`, WebSocket push, escalation | Extended |
| ML IsolationForest | `ml/anomaly_service.py` | Preserved model + feature pipeline; adds rolling z-score, model version, explanation, abnormal-pattern incidents (decision support only) | Extended |
| AI incident summary | `services/ai_assistant.py` | Preserved (mock provider, clearly labelled) | Preserved |
| Dashboard metrics | `/reports/dashboard` | Preserved + role-specific dashboards under `/dashboards/*` | Extended |
| PDF/CSV reports | `/reports/generate`, `/download` | Preserved + role-scoped report types (temperature, incidents, inventory, maintenance, audit, compliance) | Extended |
| Audit logs | `/audit-logs` | Same path; system actor allowed, immutable, IP/category, filters, export | Extended |
| Security middleware | `core/middleware.py` | Preserved; adds Prometheus instrumentation | Preserved |
| Offline sweep task | in-API `asyncio` task | Moved to `app/workers/` scheduler (worker container); embedded mode for local dev | Moved |
| Seed scripts | `scripts/seed*.py` | `scripts/seed_demo.py` (regions, facilities, 5 roles) + `/demo/reset` | Replaced |
| Simulator | `simulator/simulator.py` (HTTP) | MQTT multi-sensor simulator with 6 scenarios; HTTP mode kept; readings flagged `is_simulated` | Extended |

## Frontend

| Original page | Redesigned location |
|---|---|
| `Login.tsx` | `features/authentication/LoginPage.tsx` (demo account picker) |
| `Dashboard.tsx` (one for all) | Five role dashboards: `features/admin/AdminOverview`, `features/operator/FacilityDashboard`, `features/supervisor/RegionalOverview`, `features/technician/WorkOrdersDashboard`, `features/auditor/AuditorHome` |
| `IncidentList.tsx`, `IncidentDetails.tsx` | `features/incidents/*` (timeline, corrective actions, review panel, evidence chart) |
| `StorageUnits.tsx` | `features/monitoring/StorageUnitsPage` + live monitoring |
| `Sensors.tsx` | `features/admin/DeviceRegistryPage` + technician equipment health |
| `Products.tsx`, `Batches.tsx` | `features/inventory/*` (batches, FEFO, movements, quarantine queue) |
| `UserManagement.tsx` | `features/admin/UsersPage` |
| `Settings.tsx` | `features/admin/SystemConfigPage` (policies, escalation, notifications) |
| `Simulator.tsx` (browser-generated random data) | `features/admin/SimulationPage` — drives the backend simulation engine; readings labelled simulated |
| `Reports.tsx` | `features/reports/ReportsPage` (role-scoped) |
| `authStore.ts` | Preserved (Zustand) — now stores permissions + refresh token |
| `api/client.ts` | Preserved; adds refresh-on-401 and typed errors |
| `StatusBadge`, `MetricCard`, `TemperatureChart`, `Timeline`, `ConfirmationDialog` | Rebuilt in `components/common`, `components/charts`, `components/incidents` |
