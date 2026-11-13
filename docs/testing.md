# Testing

ColdGuard utilizes `pytest` for the backend.

## Test Suites

1. **Unit Tests**:
   - Tests core domain logic isolated from the database (e.g., `DataQualityEngine`, `SeverityEngine`).
2. **Integration Tests**:
   - Uses an in-memory SQLite database (or a test PostgreSQL instance) to verify the flow of data across engines.
3. **Scenario Tests**:
   - Found in `backend/tests/scenarios/`. These are complex, multi-stage tests that verify business workflows from start to finish.
   - Example: `test_demo_scenario.py` verifies the complete 20-step lifecycle of an incident, from initial telemetry ingestion to QA closure.

## Running Tests Locally
From the `backend/` directory:
```bash
python -m pytest tests/ -v
```
*(Ensure your virtual environment is activated).*
