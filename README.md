# ColdGuard — Vaccine Cold-Chain Monitoring & Management Platform (v2)

ColdGuard monitors vaccine storage temperatures, raises and manages incidents, tracks vaccine
batches end-to-end and coordinates equipment maintenance — with five separated roles and
server-enforced, facility-scoped access control.

> ColdGuard supports, and does not replace, clinical and regulatory decisions. ML signals are
> decision support only; no stock is ever released or discarded automatically.

## Option A — Docker Compose (full stack, recommended)

```powershell
copy .env.example .env          # replace every change-me value (UI_PORT if 8080 is taken)
docker compose up -d --build
```

| URL | What |
|---|---|
| http://localhost:8080 (or `UI_PORT`) | ColdGuard UI |
| http://localhost:8001/docs | API / OpenAPI |
| http://localhost:3000 | Grafana — 4 ColdGuard dashboards |
| http://localhost:9090 | Prometheus |
| mqtt://localhost:1883 | MQTT broker (devices publish `coldguard/telemetry/<facility>/<sensor>`) |

Stack: PostgreSQL, Redis, Mosquitto (auth + ACL), one-shot migrate/seed job, API, background worker
(MQTT ingestion, sweeps, escalation, simulation), nginx frontend, Prometheus, Grafana, exporters.
Optional MQTT device simulator: `docker compose --profile mqtt-sim up -d simulator`.
Production overrides: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`.

## Option B — Kubernetes (kind / minikube)

```bash
bash scripts/ci/build-images.sh    # coldguard-backend:2.0.0, coldguard-frontend:2.0.0
bash scripts/ci/k8s-deploy.sh      # kind cluster + ingress-nginx + metrics-server, random git-ignored secrets
bash scripts/ci/k8s-smoke.sh       # end-to-end checks (ingress, RBAC, MQTT, metrics, HPA, rollout, persistence)
```

UI at http://coldguard.localhost:8088. The deploy scripts only target local contexts (`kind-*`,
`minikube`, …). Details (topology, probes, HPA, NetworkPolicies, secrets, production overlay):
[docs/KUBERNETES.md](docs/KUBERNETES.md).

## CI/CD

`Jenkinsfile` runs the phases in `scripts/ci/`: backend/frontend tests, Compose↔k8s config
consistency, security scan, image build, Compose smoke test, kind deploy + smoke test, and gated
registry push / production deploy. Run the same thing locally with `bash scripts/ci/run-all.sh`.
See [docs/jenkins_setup.md](docs/jenkins_setup.md).

## Option C — Local development (no Docker)

```powershell
cd backend; python -m venv venv; .\venv\Scripts\activate; pip install -r requirements-dev.txt
$env:DATABASE_URL="sqlite:///./coldguard_v2.db"
python scripts/migrate.py; python scripts/seed.py
python -m uvicorn app.main:app --port 8000          # API + embedded worker + simulator
cd ..\frontend; npm install; npm run dev            # http://localhost:5173
```

> `backend/.env` from v1 still points at the original `coldguard.db` (left untouched). Use the
> `DATABASE_URL` above or edit `.env` (see `backend/.env.example`).

## Demo credentials (local demonstration only)

All seeded application accounts use the password **`ColdGuard#2026`**. On the login page you can
also just click a role under *Local demo accounts*.

| Role | Email | Scope | Lands on |
|---|---|---|---|
| System Administrator | `admin@coldguard.local` | all facilities | Global overview |
| Facility Operator | `operator.blr@coldguard.local` | 3 Bengaluru facilities | Facility dashboard |
| Facility Operator | `operator.mys@coldguard.local` | 2 Mysuru facilities | Facility dashboard |
| Regional Supervisor | `supervisor@coldguard.local` | Bengaluru Urban region | Regional overview |
| Regional Supervisor | `supervisor.south@coldguard.local` | Mysuru + Belagavi regions | Regional overview |
| Maintenance Technician | `technician@coldguard.local` | 4 Bengaluru facilities | My work orders |
| Maintenance Technician | `technician.mys@coldguard.local` | Mysuru + Belagavi facilities | My work orders |
| Auditor / Compliance | `auditor@coldguard.local` | all facilities (read-only) | Compliance overview |

Infrastructure logins come from `.env` (never committed): Grafana `GRAFANA_ADMIN_USER` /
`GRAFANA_ADMIN_PASSWORD`; MQTT devices `coldguard-device` / `MQTT_DEVICE_PASSWORD`; REST gateway
header `X-Ingest-Key: INGEST_API_KEY`.

Notes: 5 failed logins lock an account for 15 minutes. A password changed on the Profile page
replaces the demo password for that account until the demo data is reset (*Admin → Demo
simulation → Reset demo data* or `python scripts/seed.py --reset`). v1 accounts (`@coldguard.com`)
were not migrated. All demo sensors/readings are labelled **Simulated**.

## Tests

```powershell
cd backend;  python -m pytest tests -q        # 191 tests
cd frontend; npm test                         # 20 tests (run from an uppercase C:\ path on Windows)
cd backend;  python ml/evaluate.py            # ML evaluation on the SIMULATED dataset
```

## Highlights

| Area | Highlights |
|---|---|
| RBAC | 5 roles, 44 permissions in one matrix, facility/region scope on every query, 404 for out-of-scope data — [docs/RBAC.md](docs/RBAC.md) |
| Auth | JWT access (memory) + rotating refresh tokens with reuse detection, lockout, audited failures |
| Monitoring | MQTT / REST / simulator → validation → quarantine → policy thresholds → incidents; missing-telemetry vs offline; stale data flagged |
| Incidents | DETECTED → … → CLOSED, immutable timeline, supervisor approvals, background escalation |
| Inventory | Batch quantities, FEFO, immutable ledger, supervisor-only release/disposal |
| Maintenance | Work orders, calibration offsets, equipment replacement, RULE vs ML auto-tickets |
| ML | IsolationForest (v1 kept, v2 calibrated) + rolling z-score; versioned, explained, decision support |
| Excursion routing | Admin plans relocation of at-risk stock: GBR quantile ETA model (p50/p90), capacity- & hold-time-aware trips, baseline comparison, approval workflow — [docs/logistics.md](docs/logistics.md) |
| UI | Role dashboards, geographic facility maps, live WebSocket updates, notification centre |
| Ops | Multi-stage non-root images, Compose + kustomize (HPA, PDB, NetworkPolicies), Prometheus alerts, Grafana dashboards |

Docs: [EXISTING_ARCHITECTURE](docs/EXISTING_ARCHITECTURE.md) · [FEATURE_MAPPING](docs/FEATURE_MAPPING.md) ·
[ARCHITECTURE](docs/ARCHITECTURE.md) · [API](docs/API.md) · [RBAC](docs/RBAC.md) ·
[DEPLOYMENT](docs/DEPLOYMENT.md) · [SECURITY](docs/SECURITY.md)
