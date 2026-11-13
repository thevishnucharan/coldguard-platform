# ColdGuard Observability Guide

ColdGuard is instrumented for deep observability, providing structured JSON logging and a rich set of business telemetry metrics out of the box.

## 1. Structured Logging

All logs emitted by the backend application (including standard `logger.info`, `logger.error`, and Uvicorn access/error logs) are automatically formatted as JSON. 

This ensures that cloud log aggregators (like Azure Log Analytics / Application Insights) can automatically parse the severity, timestamp, module, and custom `extra` properties without requiring complex regex grok filters.

### Sensitive Data Scrubbing
ColdGuard logs are scrubbed *before* they are printed to `stdout`. Any dictionary key or string matching sensitive identifiers (e.g., `password`, `token`, `secret`, `api_key`) is intercepted and its value is replaced with `***MASKED***`.

**Never** log raw tokens or PII directly, but rely on the filter as a safety net.

## 2. Telemetry & Metrics

Business and operational metrics are tracked using the `track_metric` interface found in `app.core.telemetry`.

Currently, the following metrics are recorded:

| Metric Name | Type | Description |
|---|---|---|
| `api_requests` | Counter | Incremented on every API call (includes path/method/status) |
| `api_latency_sum` | Histogram / Sum | The total processing time of API requests |
| `processing_events` | Counter | Number of sensor readings ingested |
| `processing_latency_sum`| Histogram / Sum | Time taken to process a batch of telemetry events |
| `readings_processed` | Counter | Valid readings written to the database |
| `readings_rejected` | Counter | Readings rejected by the Quality Engine |
| `violations_detected` | Counter | When a temperature reading breaches boundaries |
| `incidents_created` | Counter | When a violation escalates into an Incident |
| `incidents_resolved` | Counter | When an Incident's root cause and corrective action are recorded |
| `alert_failures` | Counter | When an email or push notification fails to send |

### Local Development
In a local environment, `track_metric` maintains an in-memory dictionary. It also emits a structured JSON log that looks like:
```json
{"metric_name": "violations_detected", "metric_value": 1.0, "metric_properties": {"violation_type": "HIGH_EXCURSION"}}
```
You can view these metrics locally by querying the telemetry module if a health endpoint is exposed, or simply by watching the console logs.

## 3. Azure Monitor / Application Insights Integration

ColdGuard is designed to plug directly into **Azure Application Insights**.

When migrating from local to Azure:
1. Ensure the `APPLICATIONINSIGHTS_CONNECTION_STRING` is injected into the container (via Azure Key Vault / Workload Identity).
2. Install the `azure-monitor-opentelemetry` SDK in `backend/requirements.txt`:
   ```bash
   pip install azure-monitor-opentelemetry
   ```
3. Update `app/core/logging.py` and `app/core/telemetry.py` to initialize the Azure exporter. The structured JSON logs will automatically flow to the traces table, and the `track_metric` calls can be routed to the custom metrics API.

No credentials or external services are required to run this observability stack locally.
