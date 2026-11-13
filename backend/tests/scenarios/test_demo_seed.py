"""The demo dataset builds through the real services and yields a consistent, multi-role world."""
from app.models import Incident, InventoryMovement, MaintenanceTicket, TemperatureReading, User
from app.models.enums import IncidentStatus
from app.services import demo_seed


def test_demo_seed_end_to_end(db, client):
    summary = demo_seed.seed(db, history_hours=2, step_minutes=10, history_days=1)
    assert summary["facilities"] == 8 and summary["users"] == 8
    statuses = {i.status for i in db.query(Incident)}
    assert {IncidentStatus.OPEN, IncidentStatus.CORRECTIVE_ACTION_PENDING, IncidentStatus.CLOSED} <= statuses
    assert db.query(TemperatureReading).filter(TemperatureReading.is_simulated.is_(False)).count() == 0
    assert db.query(InventoryMovement).count() > 20
    assert db.query(MaintenanceTicket).count() >= 3
    # every demo account can sign in and open its own dashboard
    for email, path in (("admin@coldguard.local", "admin"), ("operator.blr@coldguard.local", "operator"),
                        ("supervisor@coldguard.local", "supervisor"), ("technician@coldguard.local", "technician"),
                        ("auditor@coldguard.local", "auditor")):
        tok = client.post("/api/v1/auth/login", data={"username": email, "password": demo_seed.DEMO_PASSWORD}).json()
        r = client.get(f"/api/v1/dashboards/{path}", headers={"Authorization": f"Bearer {tok['access_token']}"})
        assert r.status_code == 200, (email, r.text)
    assert db.query(User).count() == 8
