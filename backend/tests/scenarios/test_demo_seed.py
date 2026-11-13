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


def test_demo_seed_includes_supply_chain_scenarios(db, client):
    """Seeded relocation plans, a vehicle in transit with a failed data logger (alert + incident +
    nearby stores ranked) and a delivered shipment."""
    from app.models import RoutePlan, Shipment, TransitAlert
    from app.models.enums import IncidentType, ShipmentStatus, TransitAlertType
    summary = demo_seed.seed(db, history_hours=2, step_minutes=10, history_days=1)
    assert summary["route_plans"] >= 1 and summary["shipments"] >= 1 and summary["transit_alerts"] >= 1
    assert db.query(RoutePlan).count() == summary["route_plans"]
    moving = db.query(Shipment).filter(Shipment.status == ShipmentStatus.IN_TRANSIT).all()
    assert len(moving) == 1 and moving[0].is_simulated
    alert = db.query(TransitAlert).filter(TransitAlert.alert_type == TransitAlertType.SENSOR_FAULT).one()
    assert alert.shipment_id == moving[0].id and alert.nearby and alert.incident_id
    assert db.query(Incident).filter(Incident.incident_type == IncidentType.TRANSIT_SENSOR_FAILURE).count() == 1
    tok = client.post("/api/v1/auth/login", data={"username": "operator.blr@coldguard.local",
                                                   "password": demo_seed.DEMO_PASSWORD}).json()["access_token"]
    r = client.get("/api/v1/logistics/transit-alerts", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200 and r.json()[0]["vehicle_code"] == "KA01CC1001"
