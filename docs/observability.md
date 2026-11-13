# Observability

Prometheus scrapes every component; Grafana ships four provisioned dashboards. The same dashboard
JSON and alert rules are used by Docker Compose and Kubernetes (`scripts/ci/config-check.sh`
keeps the copies identical).

| | Docker Compose | Kubernetes |
|---|---|---|
| Prometheus | http://localhost:9090 | `kubectl -n coldguard port-forward svc/prometheus 9090` |
| Grafana | http://localhost:3000 (admin / `GRAFANA_ADMIN_PASSWORD`) | `port-forward svc/grafana 3000` |
| API / worker metrics | static targets `backend:8000`, `worker:9101` | pods discovered individually (`kubernetes_sd`, prometheus.io annotations) |
| Container CPU / memory | `container-exporter` (Docker Engine stats API, cAdvisor-compatible names; cAdvisor cannot see containers on Docker Desktop) | kubelet cAdvisor via the API server proxy (RBAC: `nodes/proxy`) |
| Container health | `container_health_status`, `container_restart_count`, `container_last_seen`, `up` | kube-state-metrics (ready, restarts), `up` |
| Database / cache | postgres-exporter (`pg_up`), redis-exporter | same |

## What is monitored

| Requirement | Metric(s) | Dashboard |
|---|---|---|
| API request count | `coldguard_http_requests_total{method,route,status}` | Application performance |
| API response time | `coldguard_http_request_duration_seconds` (p95 per route) | Application performance |
| API error rate | 5xx share of requests; `coldguard_http_errors_total` | Application performance (+ alert > 5 %) |
| CPU and memory | `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `process_*` | Infrastructure health |
| Container health | `up`, `kube_pod_container_status_ready`, `..._restarts_total`, `container_last_seen` | Infrastructure health |
| Database availability | `pg_up`, `pg_stat_activity_count` | Infrastructure health (+ alert) |
| MQTT connection status | `coldguard_mqtt_connected` (worker) | IoT telemetry (+ alert) |
| Sensor ingestion rate | `coldguard_telemetry_accepted_total` / `_rejected_total` / `_duplicates_total`, `coldguard_ingest_duration_seconds` | IoT telemetry (+ alert when it stops) |
| Incident generation rate | `coldguard_incidents_created_total{type,severity}`, `coldguard_active_incidents`, escalations, transitions | Incident monitoring |
| Background worker status | `coldguard_worker_last_heartbeat_timestamp`, `coldguard_worker_job_duration_seconds`, `..._failures_total` | Application performance (+ alert when stale) |

Alert rules (`infrastructure/prometheus/alerts.yml`): API down, worker stale, MQTT disconnected,
5xx above 5 %, ingestion stopped, database down.

**Several uvicorn workers:** with `UVICORN_WORKERS > 1` (Compose runs 2), each process has its
own counters. The entrypoint then enables prometheus_client multiprocess mode
(`PROMETHEUS_MULTIPROC_DIR`), and `/metrics` aggregates every worker process. This is covered by
`tests/unit/test_security_controls.py::test_metrics_aggregate_across_uvicorn_worker_processes`.

## Structured logs

The backend writes one JSON object per line (`app/core/logging.py`): `ts`, `level`, `logger`,
`msg`, plus request fields from `ObservabilityMiddleware` (`request_id`, method, route, status,
duration). The incoming `X-Request-ID` is propagated or generated, and returned in the response
header.

Sensitive data never reaches the log stream:
* keys named `password`, `token`, `secret`, `api_key`, `authorization`, `access_token`,
  `refresh_token`, `device_key` or `email` are replaced with `***MASKED***`;
* `password=…` / `token: …` patterns inside messages are masked;
* login failures are logged and audited without the submitted e-mail or password (tested in
  `test_security_controls.py`).

Container logs are rotated by Docker (`json-file`, 10 MB × 3) in Compose and by the kubelet in
Kubernetes. Any log shipper that reads JSON lines (Loki/Promtail, Fluent Bit, Azure Monitor) can
ingest them without parsing rules.

## Verified by CI

`compose-smoke.sh` and `k8s-smoke.sh` assert that every Prometheus target is `up`, that the MQTT,
worker-heartbeat, `pg_up`, `redis_up`, request and ingestion series have data (after real REST
and MQTT readings are sent), that container CPU/memory series exist, and that Grafana has the
four dashboards and the Prometheus datasource while rejecting anonymous access.
