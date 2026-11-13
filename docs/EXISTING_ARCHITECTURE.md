# ColdGuard — Existing Architecture Audit (pre-redesign)

> Audit date: 2026-11-12. Performed by inspecting every source file in the repository
> **before** any modification. Baseline test run: `121 passed, 1 failed, 6 errors`
> (`pytest tests` in `backend/`, Python 3.14 venv). All 7 failures share one cause — see §4.1.

## 1. Technology stack (as found)

| Layer | Technology | Notes |
|---|---|---|
| Frontend | React 19, TypeScript 6, Vite 8, Tailwind v4, Recharts 3, Zustand 5, axios, react-router 7, lucide-react, react-hot-toast | Single SPA, 12 page components (~6.3k LOC) |
| Backend | FastAPI, SQLAlchemy 2.0 (typed `Mapped[]`), Pydantic v2, pydantic-settings | Layered: `api/` → `services/` → `repositories/` → `models/` |
| DB | SQLite locally (`backend/coldguard.db`, created with `create_all`), PostgreSQL 15 in Docker Compose | One Alembic revision `8bda373ce97a_initial_schema` |
| Auth | Local JWT (python-jose, HS256), passlib bcrypt | Token carries `email` + `role` claims |
| Messaging | In-process `asyncio.Queue` ("local") or Azure Event Hubs adapter | **No MQTT** |
| ML | scikit-learn IsolationForest (`backend/ml/models/isolation_forest.joblib`) + pandas features | Trained on synthetic data by `ml/train_prototype.py` |
| AI | `MockAIProvider` incident summary (template text) | Azure OpenAI stub |
| Reports | reportlab PDF, CSV (with CSV-injection sanitising) | Local disk or Azure Blob |
| Containers | `backend/Dockerfile` (single-stage, root user), `frontend/Dockerfile` (Vite **dev server**, node 18), `simulator/Dockerfile` | `docker-compose.yml`: postgres, backend, frontend, simulator |
| Kubernetes | `infrastructure/kubernetes/*.yaml`: namespace, configmap, secret template, backend/frontend Deployment+Service, ingress | Images point to `<YOUR_ACR_NAME>`; no DB/broker/HPA/PVC |
| CI | `Jenkinsfile` (lint, test, build, ACR push, AKS deploy gated) | Not executed in this audit |
| Observability | `core/telemetry.py` in-memory counters + JSON logs | No Prometheus/Grafana |

## 2. Backend inventory

### 2.1 API routers (`backend/app/api`)
| Router | Endpoints | Authorization (as found) |
|---|---|---|
| `auth` | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | register is **public** |
| `users` | CRUD `/users` | `RequireRole([ADMIN])` |
| `configurations` | `GET/PUT /configurations/{key}` | ADMIN write |
| `storage` | CRUD `/storage-units` | ADMIN write, ADMIN/OPERATOR/AUDITOR read |
| `sensors` | CRUD `/sensors`, `/sensors/health`, `/sensors/{id}/health` | same |
| `products`, `batches` | CRUD | ADMIN write |
| `temperature` | `POST /temperature/readings`, `/readings/bulk`, `GET /readings` | ADMIN/OPERATOR ingest |
| `incidents` | list, get, acknowledge, investigate, resolve, close, assign, affected-batches, ai-summary | list/get: **any authenticated user** |
| `anomalies` | list anomalies | read roles |
| `audit` | list audit logs | ADMIN/AUDITOR |
| `reports` | `/reports/dashboard`, `/reports/generate`, `/reports/download/{file}` | |

### 2.2 Engines & services (valuable — preserved)
* `engines/quality.py` **DataQualityEngine** — impossible values, future/stale timestamps, duplicates, unrealistic jump rate.
* `engines/violation.py` **ViolationEngine** — excursion state machine (open → update peak/min/duration → recover).
* `engines/severity.py` **SeverityEngine** — deviation/duration → WARNING/HIGH/CRITICAL, DB-configurable.
* `services/sensor_health.py` — stuck sensor, abnormal frequency, unrealistic jump, offline sweep.
* `services/incident.py` — lifecycle + **affected-batch identification** by time-window overlap.
* `services/alert.py` + `adapters/notification.py` — console/SMTP alert dispatch per severity.
* `ml/anomaly_service.py` + `ml/features.py` — IsolationForest scoring on 10-reading rolling features.
* `services/reporting.py` — PDF/CSV with formula-injection protection.
* `core/middleware.py` — security headers, in-memory rate limiter, request logging.
* `core/logging.py` — JSON logs + sensitive-value masking.

### 2.3 Data model (14 tables)
`users, storage_units, sensors, products, batches, temperature_readings, sensor_health_events,
anomalies, violations, incidents, incident_batches, alerts, audit_logs, system_configurations`.
There is **no** concept of region, facility, inventory quantity, inventory movement, maintenance,
calibration, notification inbox, corrective action, or incident event history.

## 3. Frontend inventory
* `App.tsx` — flat route table; `AppLayout` sidebar hides only *Users/Settings* for non-admins.
* Pages: Dashboard, IncidentList, IncidentDetails, StorageUnits, Sensors, Products, Batches,
  UserManagement, Settings, Simulator, Reports, Login.
* Role checks are scattered string comparisons (`user?.role === 'ADMIN'`) in 8 files.
* `services/*.ts` — 11 thin axios wrappers (42 API calls), all hitting real endpoints (no static mocks,
  except the browser-side Simulator page which fabricates readings with `Math.random()` and POSTs them).
* UI copy claims "21 CFR Part 11 Active", "SHA-256 state hashing", "Site: US-East-1 Hub", "v2.4.0"
  — none of which is implemented. These claims are removed in the redesign.

## 4. Discovered issues

### 4.1 Defects
1. **Schema drift breaks PostgreSQL deployment.** Migration `8bda373ce97a` creates
   `violationseverity = (MINOR, MAJOR, CRITICAL)` and `incidentstatus = (OPEN, INVESTIGATING, RESOLVED, CLOSED)`
   and lacks `incidents.acknowledged_at`; the models use `WARNING/HIGH/CRITICAL` and `ACKNOWLEDGED`.
   On Postgres every new violation/acknowledgement would fail. SQLite hides this (no native enums).
2. `backend/requirements.txt` is partly **UTF-16 encoded** (passlib/bcrypt/jose/httpx/email-validator lines),
   and omits `pandas, scikit-learn, joblib, reportlab, azure-eventhub, azure-storage-blob` which the code imports.
   A clean `pip install -r requirements.txt` cannot produce a working backend.
3. Failing baseline tests: `test_auth.py::test_login_user` and 6 fixtures register an ADMIN through the public
   endpoint; with `ALLOW_OPEN_ROLE_REGISTRATION=false` (backend/.env) registration returns 403, so login fails.
4. Local SQLite DB has no `alembic_version` table (created via `create_all`) — migrations cannot be applied.
5. Incident numbers are `count()+1` per year → race condition / duplicates under concurrency.
6. `MetricsService` counts "open incidents" as only OPEN+INVESTIGATING (ignores ACKNOWLEDGED).
7. `temperature.py` bulk ingest validates only the **first** reading's sensor/unit.
8. ML anomalies are written to `anomalies` but never surfaced in incidents, UI, or alerts.

### 4.2 Security weaknesses
1. Public `/auth/register`; Docker Compose sets `ALLOW_OPEN_ROLE_REGISTRATION=true` → anyone can self-create an ADMIN.
2. JWT `sub` is email; role is embedded in token (not trusted later, but email reuse after rename is fragile). No refresh token, no revocation, no lockout.
3. **No facility / tenant scoping**: any OPERATOR sees and acts on every incident, unit and batch.
4. `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/{id}/affected-batches` require only authentication (AUDITOR can call `affected-batches`, which **writes** `incident_batches`).
5. Admin can close incidents and manage batches → administrative access implies clinical disposition authority.
6. Hard-coded credentials in `docker-compose.yml` (`coldguard_dev_pass`, JWT secret, simulator password).
7. Login-failure audit is written but there is no throttling beyond the per-IP limiter.
8. Audit log rows are mutable (no guard) and require a user FK, so system actions cannot be audited.

### 4.3 Architecture / responsibility problems
* Admin and Operator overlap (both acknowledge/investigate/resolve, both ingest).
* Business rules split between routers and services (e.g. role checks duplicated in `IncidentService.close`).
* Thresholds live on the storage unit only; no approved policy concept; one global "2–8 °C" default config.
* Offline sweep runs inside the API process (`asyncio` task) — scales badly with >1 replica (duplicate work).
* Notification "dashboard" channel is a console log; no in-app notification store; no real-time push.
* `core/telemetry.py` counters are per-process, not scrapeable.

### 4.4 UI/UX inconsistencies
* Same dashboard for every role; heavy gradients, pulsing icons, `animate-ping`, oversized cards.
* Unimplemented compliance claims in the sidebar.
* No loading skeletons in several pages, inconsistent table components (each page builds its own).

### 4.5 Deployment problems
* Frontend container runs the **Vite dev server** (not production-grade), on node 18 (EOL).
* Backend image runs as root, single-stage with gcc in final image.
* K8s manifests: no PostgreSQL, no PVC, no HPA, no secrets strategy beyond a template, ACR placeholders.
* No MQTT broker, Redis, worker, Prometheus or Grafana.

## 5. Recommended modifications (implemented in the redesign)
| # | Recommendation |
|---|---|
| R1 | Add `regions`, `facilities`, `user_role_assignments`; scope every query by facility/region. |
| R2 | Central permission matrix (`app/core/permissions.py`) + `require_permission()` dependency; remove role-name checks. |
| R3 | 5 roles: ADMIN, OPERATOR, SUPERVISOR, TECHNICIAN, AUDITOR; admin loses operational/clinical permissions. |
| R4 | Defensive, idempotent Alembic migration `0002` that converts native enums to VARCHAR, adds new tables/columns and back-fills existing data into a "Legacy Facility". |
| R5 | MQTT ingestion (paho-mqtt) in a dedicated worker; quarantine table for rejected telemetry; idempotency on `(sensor_id, timestamp)` + `message_id`. |
| R6 | Monitoring policies (approved min/max/warning margin/sustain time/missing-telemetry window) instead of one hardcoded range. |
| R7 | Full incident lifecycle with `incident_events` (immutable), `corrective_actions` and supervisor review. |
| R8 | Batch quantities + immutable `inventory_movements`; FEFO; quarantine/release/disposal guarded by supervisor permissions. |
| R9 | Maintenance tickets, calibration records, equipment history; rule-based auto-tickets clearly labelled. |
| R10 | Keep IsolationForest, add rolling z-score detector, store model version + explanation, never auto-disposition. |
| R11 | Notifications table + WebSocket push (Redis pub/sub bridge between worker and API). |
| R12 | Prometheus `/metrics`, Grafana dashboards, multi-stage non-root images, nginx-served frontend, Redis, Mosquitto. |
| R13 | Kubernetes manifests (kustomize) incl. Postgres StatefulSet, Mosquitto, Redis, worker, HPA, PVCs, probes. |
| R14 | Refresh-token rotation, account lockout, remove public role registration. |
