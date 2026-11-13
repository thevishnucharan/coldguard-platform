"""Prometheus instrumentation shared by API and worker processes.

The API may run several uvicorn worker processes (UVICORN_WORKERS > 1). Each process has its
own in-memory registry, so a scrape would only see the one process that answered. The
entrypoint then sets PROMETHEUS_MULTIPROC_DIR and `/metrics` aggregates all processes via
`multiprocess.MultiProcessCollector` (see `metrics_payload`)."""
import os
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter("coldguard_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("coldguard_http_request_duration_seconds", "HTTP request latency", ["method", "route"],
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
HTTP_ERRORS = Counter("coldguard_http_errors_total", "HTTP 5xx responses", ["route"])

TELEMETRY_RECEIVED = Counter("coldguard_telemetry_received_total", "Telemetry messages received", ["channel"])
TELEMETRY_ACCEPTED = Counter("coldguard_telemetry_accepted_total", "Telemetry readings stored", ["channel", "simulated"])
TELEMETRY_REJECTED = Counter("coldguard_telemetry_rejected_total", "Telemetry readings rejected/quarantined", ["channel", "reason"])
TELEMETRY_DUPLICATES = Counter("coldguard_telemetry_duplicates_total", "Duplicate telemetry ignored", ["channel"])
INGEST_LATENCY = Histogram("coldguard_ingest_duration_seconds", "Per-reading pipeline latency")

INCIDENTS_CREATED = Counter("coldguard_incidents_created_total", "Incidents created", ["type", "severity"])
INCIDENT_TRANSITIONS = Counter("coldguard_incident_transitions_total", "Incident status transitions", ["to_status"])
ESCALATIONS = Counter("coldguard_escalations_total", "Escalations performed", ["rule"])
ANOMALIES = Counter("coldguard_anomalies_total", "Anomalies flagged", ["method"])
NOTIFICATIONS = Counter("coldguard_notifications_total", "In-app notifications created", ["level"])
MAINT_TICKETS = Counter("coldguard_maintenance_tickets_created_total", "Maintenance tickets created", ["trigger"])

MQTT_CONNECTED = Gauge("coldguard_mqtt_connected", "1 if the MQTT ingestor is connected")
WORKER_HEARTBEAT = Gauge("coldguard_worker_last_heartbeat_timestamp", "Unix time of last worker job cycle")
WORKER_JOB_DURATION = Histogram("coldguard_worker_job_duration_seconds", "Worker job duration", ["job"])
WORKER_JOB_FAILURES = Counter("coldguard_worker_job_failures_total", "Worker job failures", ["job"])
# livesum: with several uvicorn workers (PROMETHEUS_MULTIPROC_DIR set) the open-socket count is summed
# over live processes instead of being reported per pid.
WS_CONNECTIONS = Gauge("coldguard_websocket_connections", "Open WebSocket connections", multiprocess_mode="livesum")
ACTIVE_INCIDENTS = Gauge("coldguard_active_incidents", "Active incidents by severity", ["severity"])
SENSORS_BY_STATUS = Gauge("coldguard_sensors", "Sensors by status", ["status"])


def metrics_payload() -> bytes:
    """Exposition for /metrics: aggregated across uvicorn workers when multiprocess mode is on."""
    from prometheus_client import CollectorRegistry, generate_latest, multiprocess
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry)
    return generate_latest()
