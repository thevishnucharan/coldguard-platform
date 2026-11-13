# ColdGuard Automated Demo Scenario Guide

This guide documents the automated end-to-end demo scenario for ColdGuard, demonstrating temperature excursion detection, incident lifecycle resolution, batch association, alerting, audit trails, and reporting.

---

## 1. Scenario Specifications

| Parameter | Value | Description |
|---|---|---|
| **Storage Unit** | `FR-001` | Walk-in Refrigerator (Pharmacy Main Vault, Floor 1) |
| **Product** | `Insulin` | Recombinant Human Insulin (Biologics / Endocrine) |
| **Batch** | `INS-2026-001` | Active batch stored in unit `FR-001` |
| **Allowed Temperature** | `2.0°C – 8.0°C` | Regulatory cold chain compliance range |
| **Simulated Readings** | 16 sequential telemetry readings | Ingested at 5-minute virtual intervals |

### Temperature Telemetry Profile
```text
Baseline:   4.0°C  →  4.3°C  →  4.2°C  →  4.5°C  →  5.1°C   (Normal monitoring)
Rise:       6.2°C  →  7.4°C                                   (Approaching limit)
Excursion:  8.6°C  →  9.7°C  → 10.5°C  → 11.4°C (PEAK)        (Violation triggered)
Cooling:   10.2°C  →  8.4°C                                   (HVAC intervention)
Recovery:   7.1°C  →  6.0°C  →  5.2°C                         (In-bounds restored)
```

---

## 2. The 20 Demo Steps & Expected Results

| Step # | Stage | Action / Event | Expected System Outcome |
|---|---|---|---|
| **01** | **Normal Monitoring** | Ingest 5 baseline readings: `[4.0, 4.3, 4.2, 4.5, 5.1]°C` | Readings stored as `valid`. Active violations: 0. Status: NOMINAL. |
| **02** | **Temperature Rises** | Ingest readings `6.2°C` and `7.4°C` | Trend tracked by quality engine. Readings still within `[2.0°C, 8.0°C]`. |
| **03** | **Warning / Violation Detected** | Ingest `8.6°C` (> `8.0°C` upper bound) | `ViolationEngine` detects threshold breach. Violation created (`OPEN`, type `HIGH_EXCURSION`). |
| **04** | **Excursion Continues** | Ingest `9.7°C` and `10.5°C` | Existing violation updated. No duplicate violations spawned. |
| **05** | **Peak Calculated** | Ingest peak reading `11.4°C` | Peak recorded as `11.4°C`. Max deviation calculated as `+3.4°C`. |
| **06** | **Duration Calculated** | Ingest intermediate elevated readings `10.2°C`, `8.4°C` | Duration calculated as 25 minutes (1,500 seconds elapsed). |
| **07** | **Severity Assigned** | Severity Engine re-evaluates | Deviation (`3.4°C`) + duration (`25m`) assigns `ViolationSeverity.HIGH`. |
| **08** | **Incident Created** | Violation triggers incident creation | Auto-generates incident `INC-2026-00001` with status `OPEN`. |
| **09** | **Affected Batch Identified** | Query active batches in storage unit during excursion window | Batch `INS-2026-001` (Insulin) flagged as `POTENTIALLY AFFECTED BATCH`. |
| **10** | **Alert Generated** | Alert service dispatches notification | Real-time alert dispatched to operator dashboard and email queue. |
| **11** | **Operator Acknowledges** | Duty Operator submits acknowledgment notes | Incident status transitions to `ACKNOWLEDGED`. Audit log created. |
| **12** | **Operator Investigates** | Duty Operator dispatches technician | Incident status transitions to `INVESTIGATING`. Work notes appended. |
| **13** | **Root Cause Entered** | Operator records engineering root cause | "Primary evaporator blower fan tripped due to transient electrical surge; auxiliary airflow damper failed to actuate automatically." |
| **14** | **Corrective Action Entered** | Operator records corrective action | "Reset evaporator circuit breaker, replaced auxiliary airflow damper actuator, switched refrigeration unit to secondary redundant compressor, and verified steady airflow." |
| **15** | **Temperature Returns to Normal** | Ingest recovery sequence `[7.1, 6.0, 5.2]°C` | First in-bounds reading (`7.1°C` <= `8.0°C`) automatically marks violation `RESOLVED`. |
| **16** | **Incident Resolved** | Operator resolves incident with Root Cause & Corrective Action | Status transitions to `RESOLVED` with UTC timestamp. |
| **17** | **Incident Closed** | Admin / QA Compliance Officer performs final closure | Status transitions to terminal state `CLOSED` with sign-off notes. |
| **18** | **Audit Trail Created** | Verify 21 CFR Part 11 append-only audit trail | Confirms 4 immutable audit records for ACK, INVESTIGATING, RESOLVE, and CLOSE transitions. |
| **19** | **Report Generated** | Reporting engine generates operational summaries | Exports compliance `PDF` and `CSV` files to `backend/reports/` with metrics and legal disclaimer. |
| **20** | **Dashboard Metrics Updated** | Metrics service aggregates real-time KPIs | Dashboard shows 16 total readings, 1 violation, 1 resolved incident, and peak temp `11.4°C`. |

---

## 3. How to Run the Demo

### Method 1: Interactive / Presentation Mode (with live delays)
Runs the demo with visual delays between readings for demonstrations:

```powershell
cd c:\RVCE\CI\coldguard\backend
.\venv\Scripts\python.exe scripts/run_demo.py --delay 0.3
```

### Method 2: Fast Execution Mode (Instant verification)
Resets the database and executes all 20 steps immediately:

```powershell
cd c:\RVCE\CI\coldguard\backend
.\venv\Scripts\python.exe scripts/run_demo.py --delay 0
```

### Method 3: Keep Existing Database (No Reset)
If you wish to run the scenario without dropping existing database tables:

```powershell
.\venv\Scripts\python.exe scripts/run_demo.py --no-reset
```

### Method 4: Automated CI / Pytest Regression
Runs the demo scenario as part of the automated test suite:

```powershell
cd c:\RVCE\CI\coldguard\backend
.\venv\Scripts\python.exe -m pytest tests/scenarios/test_demo_scenario.py -v
```

---

## 4. Default Seeded Credentials for Demo

When the demo resets the database, it creates the following ready-to-use user accounts:

| Role | Email | Password | Access Level |
|---|---|---|---|
| **Admin** | `admin@coldguard.com` | `AdminPass123!` | Incident closure, user management, reports |
| **Operator** | `operator@coldguard.com` | `OperatorPass123!` | Telemetry, incident acknowledgement & investigation |
| **Auditor** | `auditor@coldguard.com` | `AuditorPass123!` | Read-only audit logs & compliance reviews |

---

## 5. Generated Artifacts
- **Database**: `coldguard/backend/coldguard.db` (reset and populated with the completed scenario).
- **PDF Report**: `coldguard/backend/reports/coldguard_report_<id>.pdf`
- **CSV Export**: `coldguard/backend/reports/coldguard_report_<id>.csv`
