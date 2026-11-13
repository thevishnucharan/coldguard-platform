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

```
infrastructure/k8s/
  base/                 namespace, data (Postgres StatefulSet+PVC, Redis+PVC, Mosquitto),
                        app (migrate Job, API Deployment+HPA+PDB, worker, frontend+HPA, Ingress),
                        monitoring (Prometheus, Grafana, exporters), NetworkPolicies (default deny)
  overlays/local/       demo mode, 1 replica, local images, secrets from secrets.env (git-ignored)
```

Probes: API `startupProbe`/`livenessProbe` on `/health`, `readinessProbe` on `/ready` (DB check);
worker on `/metrics`; frontend on `/healthz`. API and worker pods run an init container
(`scripts/wait_for_migrations.py`) so they only start once the `coldguard-migrate` Job has brought
the schema to head. Rolling updates use `maxUnavailable: 0`; the worker uses `Recreate` so there is
never more than one scheduler / MQTT consumer.

### Local cluster with kind (tested)

```powershell
kind create cluster --name coldguard
docker compose build migrate frontend                       # builds coldguard-backend:2.0.0, coldguard-frontend:2.0.0
kind load docker-image coldguard-backend:2.0.0 coldguard-frontend:2.0.0 --name coldguard
copy infrastructure\k8s\overlays\local\secrets.env.example infrastructure\k8s\overlays\local\secrets.env   # edit values
kubectl --context kind-coldguard apply -k infrastructure/k8s/overlays/local
kubectl --context kind-coldguard -n coldguard wait --for=condition=complete job/coldguard-migrate --timeout=600s
kubectl --context kind-coldguard -n coldguard rollout status deploy/backend deploy/worker deploy/frontend
kubectl --context kind-coldguard -n coldguard port-forward svc/frontend 8088:80     # http://localhost:8088
```

Always pass `--context` so commands never hit another cluster in your kubeconfig.
The HPAs need metrics-server (`kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml`, add `--kubelet-insecure-tls` on kind).
The Ingress expects an NGINX ingress controller (host `coldguard.local`).
Minikube: `minikube image load …` instead of `kind load`, then the same `kubectl apply -k`.

### Production notes
* Push images to a registry and set them with `kustomize edit set image` in a production overlay.
* Replace `secretGenerator` with External Secrets / Sealed Secrets; never commit `secrets.env`.
* Prefer managed PostgreSQL: remove the StatefulSet and point `DATABASE_URL` at it.
* Add TLS to the Ingress (cert-manager) and a TLS listener to Mosquitto (LoadBalancer :8883).

## 3. Observability
* Metrics: API `/metrics` (request rate, latency histogram, 5xx, telemetry accepted/rejected/duplicates,
  ingest latency, incidents, escalations, anomalies, notifications, WebSocket clients) and worker `:9101/metrics`
  (MQTT connected, heartbeat, job duration/failures, active incidents, sensors by status, process CPU/RSS).
* Grafana dashboards: *Infrastructure health*, *Application performance*, *IoT telemetry*, *Incident monitoring*
  (`infrastructure/grafana/dashboards`).
* Prometheus alert rules (`infrastructure/prometheus/alerts.yml`): API down, worker stale, MQTT disconnected,
  5xx > 5 %, ingestion stopped, database down.
* Logs: one JSON object per line with request id, route, status and duration; secrets and e-mail addresses masked.
