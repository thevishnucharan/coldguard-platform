# Deployment

## 1. Docker Compose (full stack)

```powershell
copy .env.example .env      # then replace every change-me value
docker compose up -d --build
docker compose ps           # all services healthy; 'migrate' exits 0
```

| URL | Service |
|---|---|
| http://localhost:8080 | ColdGuard UI (nginx; proxies `/api` and the WebSocket to the API) |
| http://localhost:8001/docs | API (OpenAPI) |
| http://localhost:3000 | Grafana (`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`) — folder *ColdGuard*, 4 dashboards |
| http://localhost:9090 | Prometheus (targets, alert rules) |
| mqtt://localhost:1883 | Mosquitto — devices authenticate as `coldguard-device` / `MQTT_DEVICE_PASSWORD`, publish `coldguard/telemetry/<facility>/<sensor>` |

Services: `postgres` (volume `postgres_data`), `redis`, `mosquitto` (auth + ACL), `migrate` (one-shot:
migrations, then demo seed when `DEMO_MODE=true`), `backend` (API, 2 Uvicorn workers, no embedded
worker), `worker` (MQTT ingestion, sweeps, escalation, maintenance rules, simulation, metrics :9101),
`frontend`, `prometheus`, `grafana`, `postgres-exporter`, `redis-exporter`. Optional MQTT device simulator:

```powershell
docker compose --profile mqtt-sim up -d simulator   # set SIM_API_PASSWORD in .env for discovery
```

Production overrides (no demo data, no direct API/Prometheus ports, CORS from `PUBLIC_ORIGIN`):
`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

Backups: `docker compose exec postgres pg_dump -U $env:POSTGRES_USER coldguard > backup.sql`.
Upgrades: rebuild, then `docker compose up -d` — `migrate` applies new Alembic revisions first.
The 0002 migration upgrades v1 databases in place and is intentionally not downgradable; take a backup first.

## 2. Kubernetes (kustomize)

Full guide: [KUBERNETES.md](KUBERNETES.md). The short version for a local kind cluster:

```bash
bash scripts/ci/build-images.sh   # images tagged 2.0.0
bash scripts/ci/k8s-deploy.sh     # kind-coldguard + ingress-nginx + metrics-server, overlays/local
bash scripts/ci/k8s-smoke.sh      # end-to-end verification
# UI: http://coldguard.localhost:8088
```

Overlays: `local` (demo mode, 1 replica, generated git-ignored secrets) and `production` (registry
images, TLS ingress, secrets from an external store). Always pass `--context`, so commands never
reach another cluster in your kubeconfig.

## 3. Observability

Details: [observability.md](observability.md).
* Metrics: API `/metrics` (request rate, latency histogram, 5xx, telemetry accepted/rejected/duplicates,
  ingest latency, incidents, escalations, anomalies, notifications, WebSocket clients) and worker `:9101/metrics`
  (MQTT connected, heartbeat, job duration/failures, active incidents, sensors by status, process CPU/RSS).
* Grafana dashboards: *Infrastructure health*, *Application performance*, *IoT telemetry*, *Incident monitoring*
  (`infrastructure/grafana/dashboards`).
* Prometheus alert rules (`infrastructure/prometheus/alerts.yml`): API down, worker stale, MQTT disconnected,
  5xx > 5 %, ingestion stopped, database down.
* Logs: one JSON object per line with request id, route, status and duration; secrets and e-mail addresses masked.
