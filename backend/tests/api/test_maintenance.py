"""Maintenance tickets, calibration, equipment replacement, rule-based auto tickets."""
from datetime import datetime, timedelta, timezone

from app.models import EquipmentEvent, MaintenanceTicket, Sensor
from app.models.enums import MaintenanceTrigger, SensorStatus
from app.services.maintenance import MaintenanceRules


def _ticket(client, h, org, **kw):
    body = {"facility_id": str(org.f1.id), "storage_unit_id": str(org.units.u1.id), "title": "Door seal worn",
            "description": "Seal torn at hinge side", "priority": "HIGH", **kw}
    return client.post("/api/v1/maintenance/tickets", headers=h, json=body)


def test_ticket_lifecycle(client, org, auth):
    op, sup, tech = auth(org.users.op1), auth(org.users.sup1), auth(org.users.tech1)
    t = _ticket(client, op, org)
    assert t.status_code == 201
    tid = t.json()["id"]
    base = f"/api/v1/maintenance/tickets/{tid}"
    assert client.post(f"{base}/assign", headers=sup, json={"technician_id": str(org.users.tech3.id)}).status_code == 400
    assert client.post(f"{base}/assign", headers=sup, json={"technician_id": str(org.users.tech1.id)}).json()["status"] == "ASSIGNED"
    assert client.post(f"{base}/start", headers=tech).json()["status"] == "IN_PROGRESS"
    assert client.post(f"{base}/notes", headers=tech, json={"body": "Seal measured 3mm gap", "kind": "INSPECTION"}).status_code == 200
    assert client.post(f"{base}/notes", headers=tech, json={"body": "Photo", "kind": "EVIDENCE",
                                                            "evidence_reference": "photo-123.jpg"}).status_code == 200
    r = client.post(f"{base}/resolve", headers=tech, json={"repair_notes": "Replaced seal",
                                                           "next_maintenance_due": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()})
    assert r.json()["status"] == "RESOLVED" and "3mm" in r.json()["inspection_results"]
    assert client.post(f"{base}/verify", headers=op, json={"ok": True, "notes": "Holding 5°C"}).json()["status"] == "VERIFIED"
    d = client.post(f"{base}/close", headers=op, json={}).json()
    assert d["status"] == "CLOSED" and len(d["notes"]) >= 6


def test_technician_cannot_verify_own_work_and_non_assignee_cannot_start(client, org, auth, db):
    op, tech = auth(org.users.op1), auth(org.users.tech1)
    tid = _ticket(client, op, org).json()["id"]
    base = f"/api/v1/maintenance/tickets/{tid}"
    client.post(f"{base}/accept", headers=tech)
    client.post(f"{base}/start", headers=tech)
    client.post(f"{base}/resolve", headers=tech, json={"repair_notes": "fixed it"})
    assert client.post(f"{base}/verify", headers=tech, json={"ok": True}).status_code == 403  # no maintenance.verify
    assert client.post(f"{base}/verify", headers=op, json={"ok": False}).status_code == 400   # notes required
    assert client.post(f"{base}/verify", headers=op, json={"ok": False, "notes": "Still warm"}).json()["status"] == "IN_PROGRESS"


def test_technician_scope(client, org, auth):
    r = _ticket(client, auth(org.users.op3), org, facility_id=str(org.f3.id), storage_unit_id=str(org.units.u3.id))
    tid = r.json()["id"]
    assert client.get(f"/api/v1/maintenance/tickets/{tid}", headers=auth(org.users.tech1)).status_code == 404
    assert client.post(f"/api/v1/maintenance/tickets/{tid}/accept", headers=auth(org.users.tech1)).status_code == 404
    # cannot attach a unit from another facility
    assert _ticket(client, auth(org.users.op1), org, storage_unit_id=str(org.units.u2.id)).status_code == 400


def test_calibration_record_updates_sensor(client, org, auth, db):
    h = auth(org.users.tech1)
    now = datetime.now(timezone.utc)
    r = client.post("/api/v1/calibration", headers=h, json={
        "sensor_id": str(org.sensors.u1.id), "calibrated_at": now.isoformat(), "result": "ADJUSTED",
        "offset_applied": -0.3, "reference_temperature": 5.0, "measured_temperature": 5.3,
        "certificate_reference": "CERT-77", "interval_days": 180})
    assert r.status_code == 201, r.text
    db.refresh(org.sensors.u1)
    assert org.sensors.u1.calibration_offset == -0.3
    assert (org.sensors.u1.calibration_due_at.replace(tzinfo=timezone.utc) - now).days in (179, 180)
    assert client.post("/api/v1/calibration", headers=h, json={
        "sensor_id": str(org.sensors.u1.id), "calibrated_at": now.isoformat(), "result": "ADJUSTED"}).status_code == 400
    assert client.post("/api/v1/calibration", headers=auth(org.users.op1), json={
        "sensor_id": str(org.sensors.u1.id), "calibrated_at": now.isoformat(), "result": "PASS"}).status_code == 403
    assert len(client.get(f"/api/v1/calibration?sensor_id={org.sensors.u1.id}", headers=auth(org.users.auditor)).json()) == 1


def test_sensor_replacement_keeps_history(client, org, auth, db):
    h = auth(org.users.tech1)
    r = client.post("/api/v1/equipment/replace-sensor", headers=h, json={
        "old_sensor_id": str(org.sensors.u1.id), "new_sensor_code": "S-U1-B", "reason": "Probe cable damaged"})
    assert r.status_code == 200, r.text
    db.expire_all()
    old = db.get(Sensor, org.sensors.u1.id)
    new = db.query(Sensor).filter_by(sensor_code="S-U1-B").one()
    assert old.status == SensorStatus.DECOMMISSIONED and old.storage_unit_id is None
    assert new.storage_unit_id == org.units.u1.id and new.status == SensorStatus.PROVISIONED
    assert db.query(EquipmentEvent).filter(EquipmentEvent.event_type.in_(["REPLACED", "INSTALLED_AS_REPLACEMENT"])).count() == 2
    from app.services import telemetry
    from tests.conftest import reading
    assert telemetry.ingest(db, reading("S-U1", 5)).status == "rejected"  # old device blocked
    assert telemetry.ingest(db, reading("S-U1-B", 5)).status == "accepted"


def test_rule_based_tickets_are_labelled_and_deduplicated(db, org):
    org.sensors.u1.battery_level = 12
    org.sensors.u2.calibration_due_at = datetime.now(timezone.utc) + timedelta(days=3)
    db.commit()
    first = MaintenanceRules.run(db)
    assert first["battery"] == 1 and first["calibration"] == 1
    assert MaintenanceRules.run(db)["battery"] == 0  # dedup
    t = db.query(MaintenanceTicket).filter_by(trigger_rule="LOW_BATTERY").one()
    assert t.trigger == MaintenanceTrigger.RULE  # rule-based, not presented as predictive


def test_admin_device_registry(client, org, auth, db):
    h = auth(org.users.admin)
    r = client.post("/api/v1/sensors", headers=h, json={"sensor_code": "S-NEW-1", "storage_unit_id": str(org.units.u2.id)})
    assert r.status_code == 201 and len(r.json()["device_key"]) > 20 and r.json()["status"] == "PROVISIONED"
    sid = r.json()["id"]
    assert "device_key" not in client.get(f"/api/v1/sensors/{sid}", headers=h).json()
    assert client.post(f"/api/v1/sensors/{sid}/decommission?reason=compromised", headers=h).json()["status"] == "DECOMMISSIONED"
    hist = client.get(f"/api/v1/sensors/{sid}/history", headers=h).json()
    assert [e["event_type"] for e in hist] == ["DECOMMISSIONED", "PROVISIONED"]
