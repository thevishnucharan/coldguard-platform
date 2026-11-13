# End-to-End Demo Scenario

ColdGuard provides an automated script that simulates a realistic 20-step temperature excursion in a pharmaceutical storage vault.

## The Scenario
- **Storage Unit**: FR-001 (Allowed 2.0°C – 8.0°C)
- **Product**: Insulin (Batch INS-2026-001)
- **Event**: A transient electrical surge trips the evaporator blower.

## Running the Demo
Ensure the local stack is running (or the database is accessible). From the `backend/` directory:
```bash
python scripts/run_demo.py
```

## What it Verifies
1. Ingestion of normal telemetry.
2. Ingestion of rising temperatures.
3. Automated detection of a threshold violation.
4. Tracking of the peak (11.4°C) and duration.
5. Automated generation of an Incident.
6. Automated identification of the affected Insulin batch.
7. Role-based transitions (Ack -> Investigate -> Resolve -> Close).
8. Generation of Audit Logs.
9. Export of PDF/CSV compliance reports.
