# System Workflow

The ColdGuard platform operates on a reactive, event-driven pipeline.

## 1. Event Ingestion
1. The **Sensor Simulator** (or real IoT device) generates a temperature payload (`sensor_id`, `temperature`, `timestamp`).
2. The payload is sent to the `EventConsumer` adapter.
3. The **Data Quality Engine** inspects the payload. If the temperature is out of physical bounds (e.g., -100°C) or the timestamp is invalid, it is rejected.

## 2. Violation Processing
1. Valid readings are stored in the database.
2. The **Violation Engine** checks the reading against the configured min/max thresholds of the associated Storage Unit.
3. If an excursion is detected:
   - A new Violation is created.
   - If a Violation is already open, it updates the `peak_temperature`, `duration`, and `end_time`.
4. The **Severity Engine** calculates the severity (WARNING, HIGH, CRITICAL).

## 3. Incident Generation
1. A Violation immediately spawns an **Incident**.
2. The **Affected Batch Engine** queries the database for any Product Batches whose `start_time` and `end_time` overlap with the excursion window inside that specific storage unit.
3. The **Alert Engine** fires notifications (via Email or Dashboard Mock Providers).

## 4. Incident Management Lifecycle
- **OPEN**: Incident is generated.
- **ACKNOWLEDGED**: An Operator acknowledges the alarm.
- **INVESTIGATING**: An Operator begins physical or remote investigation.
- **RESOLVED**: An Operator submits a Root Cause and Corrective Action.
- **CLOSED**: An Admin/QA validates the response and closes the incident.
*Every transition logs an immutable entry to the Audit Log.*
