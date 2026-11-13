# API Reference

Interactive OpenAPI docs: `/docs` and `/openapi.json`. Bearer access token required unless marked public.
Every endpoint also applies facility/region data scope (out-of-scope resources return 404).
Errors: `{"detail": …}` (422 adds `errors[]`). Paginated lists return `{items,total,page,page_size}`.

**WebSocket** `/api/v1/ws`: first frame `{"type":"auth","token":"…"}`; events `reading`, `sensor.status`, `incident.created`,
`incident.updated`, `maintenance.updated`, `notification`, `ping` — filtered to the user's scope.

**Probes/metrics** (no auth): `GET /health`, `GET /ready`, `GET /metrics`.

## auth

| Method | Path | Required permission(s) |
|---|---|---|
| `POST` | `/api/v1/auth/login` | public |
| `POST` | `/api/v1/auth/refresh` | public |
| `POST` | `/api/v1/auth/logout` | authenticated |
| `GET` | `/api/v1/auth/me` | authenticated |
| `POST` | `/api/v1/auth/change-password` | authenticated |

## users

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/users/roles` | `users.view` |
| `GET` | `/api/v1/users` | `users.view` |
| `GET` | `/api/v1/users/assignable` | `incidents.view` |
| `POST` | `/api/v1/users` | `users.create`, `users.assign_roles` |
| `GET` | `/api/v1/users/{user_id}` | `users.view` |
| `PUT` | `/api/v1/users/{user_id}` | `users.update` |
| `PUT` | `/api/v1/users/{user_id}/assignments` | `users.assign_roles` |
| `GET` | `/api/v1/users/{user_id}/activity` | `users.view`, `audit.view` |

## organisation

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/regions` | `facilities.view` |
| `POST` | `/api/v1/regions` | `regions.manage` |
| `PUT` | `/api/v1/regions/{region_id}` | `regions.manage` |
| `GET` | `/api/v1/facilities` | `facilities.view` |
| `POST` | `/api/v1/facilities` | `facilities.create` |
| `GET` | `/api/v1/facilities/{facility_id}` | `facilities.view` |
| `PUT` | `/api/v1/facilities/{facility_id}` | `facilities.update` |

## monitoring policies

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/policies` | `monitoring.view` |
| `POST` | `/api/v1/policies` | `platform.configure` |
| `PUT` | `/api/v1/policies/{policy_id}` | `platform.configure` |

## storage units

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/storage-units` | `monitoring.view` |
| `POST` | `/api/v1/storage-units` | `storage.manage` |
| `GET` | `/api/v1/storage-units/{unit_id}` | `monitoring.view` |
| `PUT` | `/api/v1/storage-units/{unit_id}` | `storage.manage` |
| `DELETE` | `/api/v1/storage-units/{unit_id}` | `storage.manage` |
| `GET` | `/api/v1/storage-units/{unit_id}/readings` | `monitoring.view` |

## device registry

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/sensors` | `devices.view` |
| `POST` | `/api/v1/sensors` | `devices.register` |
| `GET` | `/api/v1/sensors/health` | `devices.view` |
| `GET` | `/api/v1/sensors/{sensor_id}` | `devices.view` |
| `PUT` | `/api/v1/sensors/{sensor_id}` | `devices.register` |
| `POST` | `/api/v1/sensors/{sensor_id}/assign` | `devices.register` |
| `POST` | `/api/v1/sensors/{sensor_id}/decommission` | `devices.register` |
| `POST` | `/api/v1/sensors/{sensor_id}/rotate-key` | `devices.register` |
| `GET` | `/api/v1/sensors/{sensor_id}/health` | `devices.view` |
| `GET` | `/api/v1/sensors/{sensor_id}/history` | `devices.view` |

## monitoring

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/monitoring/live` | `monitoring.view` |
| `GET` | `/api/v1/monitoring/quarantine` | `devices.view` |
| `GET` | `/api/v1/monitoring/anomalies` | `monitoring.view` |

## telemetry gateway

| Method | Path | Required permission(s) |
|---|---|---|
| `POST` | `/api/v1/temperature/readings` | `X-Ingest-Key` or `telemetry.ingest` |
| `POST` | `/api/v1/temperature/readings/bulk` | `X-Ingest-Key` or `telemetry.ingest` |
| `GET` | `/api/v1/temperature/readings` | `monitoring.view` |

## incidents

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/incidents` | `incidents.view` |
| `POST` | `/api/v1/incidents` | `incidents.investigate` |
| `GET` | `/api/v1/incidents/{incident_id}` | `incidents.view` |
| `GET` | `/api/v1/incidents/{incident_id}/events` | `incidents.view` |
| `GET` | `/api/v1/incidents/{incident_id}/evidence` | `incidents.view` |
| `POST` | `/api/v1/incidents/{incident_id}/acknowledge` | `incidents.acknowledge` |
| `POST` | `/api/v1/incidents/{incident_id}/investigate` | `incidents.investigate` |
| `POST` | `/api/v1/incidents/{incident_id}/notes` | `incidents.investigate` |
| `POST` | `/api/v1/incidents/{incident_id}/escalate` | `incidents.escalate` |
| `POST` | `/api/v1/incidents/{incident_id}/corrective-actions` | `corrective_actions.submit` |
| `POST` | `/api/v1/incidents/{incident_id}/corrective-actions/{ca_id}/review` | `corrective_actions.approve` |
| `POST` | `/api/v1/incidents/{incident_id}/corrective-actions/{ca_id}/implement` | `corrective_actions.submit` |
| `POST` | `/api/v1/incidents/{incident_id}/verify-recovery` | `corrective_actions.submit` |
| `POST` | `/api/v1/incidents/{incident_id}/review` | `incidents.review` |
| `POST` | `/api/v1/incidents/{incident_id}/close` | `incidents.review` |
| `POST` | `/api/v1/incidents/{incident_id}/assign` | `incidents.assign` |
| `GET` | `/api/v1/incidents/{incident_id}/affected-batches` | `incidents.view`, `inventory.view` |
| `POST` | `/api/v1/incidents/{incident_id}/ai-summary` | `incidents.investigate` |

## inventory

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/products` | `inventory.view` |
| `POST` | `/api/v1/products` | `products.manage` |
| `PUT` | `/api/v1/products/{product_id}` | `products.manage` |
| `GET` | `/api/v1/batches` | `inventory.view` |
| `POST` | `/api/v1/batches/receive` | `inventory.manage` |
| `GET` | `/api/v1/batches/{batch_id}` | `inventory.view` |
| `POST` | `/api/v1/batches/{batch_id}/issue` | `inventory.manage` |
| `POST` | `/api/v1/batches/{batch_id}/adjust` | `inventory.manage` |
| `POST` | `/api/v1/batches/{batch_id}/reconcile` | `inventory.manage` |
| `POST` | `/api/v1/batches/{batch_id}/transfer` | `inventory.manage` |
| `POST` | `/api/v1/batches/{batch_id}/quarantine` | `batches.quarantine` |
| `POST` | `/api/v1/batches/{batch_id}/release` | `batches.release` |
| `POST` | `/api/v1/batches/{batch_id}/dispose` | `batches.dispose` |
| `GET` | `/api/v1/inventory/fefo` | `inventory.view` |
| `POST` | `/api/v1/inventory/issue-fefo` | `inventory.manage` |
| `GET` | `/api/v1/inventory/movements` | `inventory.view` |
| `GET` | `/api/v1/inventory/summary` | `inventory.view` |

## maintenance

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/maintenance/tickets` | `maintenance.view` |
| `POST` | `/api/v1/maintenance/tickets` | `maintenance.create` |
| `GET` | `/api/v1/maintenance/tickets/{ticket_id}` | `maintenance.view` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/assign` | `maintenance.assign` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/accept` | `maintenance.update` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/start` | `maintenance.update` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/notes` | `maintenance.update` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/resolve` | `maintenance.update` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/verify` | `maintenance.verify` |
| `POST` | `/api/v1/maintenance/tickets/{ticket_id}/close` | `maintenance.verify` |
| `GET` | `/api/v1/maintenance/schedule` | `maintenance.view` |

## calibration

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/calibration` | `calibration.view` |
| `POST` | `/api/v1/calibration` | `calibration.record` |

## equipment

| Method | Path | Required permission(s) |
|---|---|---|
| `POST` | `/api/v1/equipment/replace-sensor` | `equipment.replace` |
| `POST` | `/api/v1/equipment/replace-storage-unit` | `equipment.replace` |
| `GET` | `/api/v1/equipment/history` | `maintenance.view` |

## notifications

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/notifications` | `notifications.view` |
| `POST` | `/api/v1/notifications/{notification_id}/read` | `notifications.view` |
| `POST` | `/api/v1/notifications/read-all` | `notifications.view` |

## dashboards

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/dashboards/admin` | `platform.view`, `users.view` |
| `GET` | `/api/v1/dashboards/operator` | `monitoring.view`, `incidents.acknowledge` |
| `GET` | `/api/v1/dashboards/supervisor` | `incidents.review`, `reports.view` |
| `GET` | `/api/v1/dashboards/technician` | `maintenance.update`, `calibration.view` |
| `GET` | `/api/v1/dashboards/auditor` | `audit.view`, `reports.view` |

## analytics

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/analytics/compliance-trend` | `reports.view` |
| `GET` | `/api/v1/analytics/facility-comparison` | `reports.view`, `incidents.view` |
| `GET` | `/api/v1/analytics/incidents-per-day` | `incidents.view` |
| `GET` | `/api/v1/analytics/device-reliability` | `devices.view` |
| `GET` | `/api/v1/analytics/ingestion` | `monitoring.view` |

## reports

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/reports/types` | `reports.view` |
| `GET` | `/api/v1/reports/export` | `reports.view`, `reports.export` |
| `GET` | `/api/v1/reports/dashboard` | `platform.view` |

## audit

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/audit-logs` | `audit.view` |

## system

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/system/status` | `platform.view` |
| `GET` | `/api/v1/system/escalation-rules` | `platform.view` |
| `PUT` | `/api/v1/system/escalation-rules` | `platform.configure` |
| `GET` | `/api/v1/configurations` | `platform.view` |
| `PUT` | `/api/v1/configurations/{key}` | `platform.configure` |

## demo

| Method | Path | Required permission(s) |
|---|---|---|
| `GET` | `/api/v1/demo/simulation` | `simulation.control` |
| `POST` | `/api/v1/demo/simulation/start` | `simulation.control` |
| `POST` | `/api/v1/demo/simulation/stop` | `simulation.control` |
| `POST` | `/api/v1/demo/simulation/scenario` | `simulation.control` |
| `POST` | `/api/v1/demo/reset` | `simulation.control`, `platform.configure` |
