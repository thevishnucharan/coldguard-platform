"""Horizontal privilege escalation / cross-facility access."""
from datetime import datetime, timedelta, timezone

from app.models.enums import IncidentType, ViolationSeverity
from app.services.incident import IncidentService
from app.services.inventory import InventoryService


def _incident(db, org, unit):
    inc, _ = IncidentService.open_incident(db, incident_type=IncidentType.EQUIPMENT_FAILURE,
                                           severity=ViolationSeverity.HIGH, facility_id=unit.facility_id,
                                           storage_unit_id=unit.id, title="test incident")
    return inc


def test_operator_cannot_read_other_facility_incident(client, org, db, auth):
    inc3 = _incident(db, org, org.units.u3)
    r = client.get(f"/api/v1/incidents/{inc3.id}", headers=auth(org.users.op1))
    assert r.status_code == 404  # not 403: existence is not revealed
    assert client.post(f"/api/v1/incidents/{inc3.id}/acknowledge", headers=auth(org.users.op1), json={}).status_code == 404
    assert client.get(f"/api/v1/incidents/{inc3.id}", headers=auth(org.users.op3)).status_code == 200


def test_incident_list_is_scoped(client, org, db, auth):
    _incident(db, org, org.units.u1)
    _incident(db, org, org.units.u3)
    assert client.get("/api/v1/incidents", headers=auth(org.users.op1)).json()["total"] == 1
    assert client.get("/api/v1/incidents", headers=auth(org.users.sup1)).json()["total"] == 1
    assert client.get("/api/v1/incidents", headers=auth(org.users.auditor)).json()["total"] == 2
    r = client.get(f"/api/v1/incidents?facility_id={org.f3.id}", headers=auth(org.users.op1))
    assert r.status_code == 403


def test_supervisor_region_isolation(client, org, db, auth):
    inc3 = _incident(db, org, org.units.u3)
    assert client.get(f"/api/v1/incidents/{inc3.id}", headers=auth(org.users.sup1)).status_code == 404
    assert client.get(f"/api/v1/incidents/{inc3.id}", headers=auth(org.users.sup2)).status_code == 200
    facs = {f["code"] for f in client.get("/api/v1/facilities", headers=auth(org.users.sup1)).json()}
    assert facs == {"F1", "F2"}


def test_batches_and_stock_actions_scoped(client, org, db, auth):
    b3 = InventoryService.receive(db, org.users.op3, batch_number="B-F3", product_id=org.product.id,
                                  storage_unit_id=org.units.u3.id, quantity=100,
                                  expiry_date=datetime.now(timezone.utc) + timedelta(days=100))
    h = auth(org.users.op1)
    assert client.get(f"/api/v1/batches/{b3.id}", headers=h).status_code == 404
    assert client.post(f"/api/v1/batches/{b3.id}/issue", headers=h, json={"quantity": 1}).status_code == 404
    assert client.get("/api/v1/batches", headers=h).json()["total"] == 0
    # cannot receive stock into another facility's unit
    r = client.post("/api/v1/batches/receive", headers=h, json={
        "batch_number": "B-X", "product_id": str(org.product.id), "storage_unit_id": str(org.units.u3.id),
        "quantity": 5, "expiry_date": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()})
    assert r.status_code == 404


def test_technician_scope_and_live_monitoring_scope(client, org, auth):
    units = client.get("/api/v1/monitoring/live", headers=auth(org.users.tech1)).json()["units"]
    assert {u["unit_code"] for u in units} == {"U1", "U2", "FZ1"}
    assert client.get(f"/api/v1/storage-units/{org.units.u3.id}/readings", headers=auth(org.users.tech1)).status_code == 404
    assert client.get(f"/api/v1/sensors/{org.sensors.u3.id}", headers=auth(org.users.tech1)).status_code == 404


def test_operator_cannot_read_other_users_notifications(client, org, db, auth):
    from app.models import Notification
    n = Notification(user_id=org.users.op3.id, title="t", message="m")
    db.add(n)
    db.commit()
    assert client.post(f"/api/v1/notifications/{n.id}/read", headers=auth(org.users.op1)).status_code == 404
    assert client.get("/api/v1/notifications", headers=auth(org.users.op1)).json()["unread"] == 0


def test_supervisor_audit_view_is_region_scoped(client, org, db, auth):
    from app.services.audit import log_audit
    log_audit(db, org.users.op3, "X_F3", "Test", None, {}, facility_id=org.f3.id)
    log_audit(db, org.users.op1, "X_F1", "Test", None, {}, facility_id=org.f1.id)
    actions = {i["action"] for i in client.get("/api/v1/audit-logs", headers=auth(org.users.sup1)).json()["items"]}
    assert "X_F1" in actions and "X_F3" not in actions
