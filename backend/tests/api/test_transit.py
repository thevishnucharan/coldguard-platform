"""In-transit monitoring of relocation vehicles: dispatch, data-logger failures (fault,
implausible value, silence), cargo excursions, ML-ranked nearby cold-chain stores, alerts to the
vehicle operator / source facility / nearby facilities, incidents, divert / deliver, RBAC."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Incident, Notification, Shipment, TransitAlert, User, UserRoleAssignment
from app.models.enums import (IncidentType, Role, ShipmentStatus, TransitAlertStatus, TransitAlertType,
                              TransitSensorState, ViolationSeverity)
from app.services.inventory import InventoryService
from app.services.transit import TransitService
from tests.conftest import _HASH, feed

API = "/api/v1/logistics"
KEY = {"X-Ingest-Key": "test-ingest-key-0123456789"}
MIDWAY = {"lat": 13.0030, "lon": 77.5960}   # between F1 (12.97, 77.59) and F2 (13.035, 77.597)


@pytest.fixture
def world(org, db, client, auth):
    """F1 (source) and F2 are ~7 km apart in Bengaluru, F3 is Mysuru. A Penta batch sits in U1
    while U1 is in an excursion; an approved plan sends it to U2 (F2) in one vehicle trip."""
    org.f1.latitude, org.f1.longitude = 12.9716, 77.5946
    org.f2.latitude, org.f2.longitude = 13.0350, 77.5970
    org.f3.latitude, org.f3.longitude = 12.2958, 76.6394
    op2 = User(name="op2", email="op2@t.io", role=Role.OPERATOR, password_hash=_HASH)
    db.add(op2)
    db.flush()
    db.add(UserRoleAssignment(user_id=op2.id, role=Role.OPERATOR, facility_id=org.f2.id))
    db.commit()
    b = InventoryService.receive(db, org.users.op1, batch_number="PENTA-T1", product_id=org.product.id,
                                 storage_unit_id=org.units.u1.id, quantity=1000,
                                 expiry_date=datetime.now(timezone.utc) + timedelta(days=200))
    b.start_time = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    feed(db, "S-U1", [5, 9.8, 9.9, 10.2], start_minutes_ago=5)
    inc = db.query(Incident).filter(Incident.incident_type == IncidentType.TEMPERATURE_EXCURSION).one()
    h = auth(org.users.admin)
    plan = client.post(f"{API}/route-plans", headers=h, json={"incident_id": str(inc.id)}).json()
    assert client.post(f"{API}/route-plans/{plan['id']}/approve", headers=h, json={}).status_code == 200
    org.op2, org.plan, org.excursion = op2, plan, inc
    return org


def _dispatch(client, auth, w, user=None, **body):
    body = {"vehicle_code": "KA01CC1001", **body}
    return client.post(f"{API}/route-plans/{w.plan['id']}/dispatch", headers=auth(user or w.users.op1), json=body)


def _shipment(client, auth, w):
    r = _dispatch(client, auth, w)
    assert r.status_code == 201, r.text
    return r.json()[0]


def _reading(client, sid, headers=KEY, **body):
    return client.post(f"{API}/shipments/{sid}/telemetry", headers=headers, json={**MIDWAY, **body})


def _notes(db, user, contains):
    return db.query(Notification).filter(Notification.user_id == user.id, Notification.title.contains(contains)).count()


# --------------------------------------------------------------------------- dispatch
def test_dispatch_creates_a_tracked_shipment(client, world, auth, db):
    s = _shipment(client, auth, world)
    assert s["status"] == "IN_TRANSIT" and s["sensor_state"] == "OK" and s["vehicle_code"] == "KA01CC1001"
    assert s["sensor_code"] == "VDL-KA01CC1001"
    assert s["temperature_range"] == [2.0, 8.0] and s["hold_minutes"] == 240 and s["total_doses"] == 1000
    assert (s["last_lat"], s["last_lon"]) == (12.9716, 77.5946)          # starts at the source facility
    assert [st["facility_code"] for st in s["stops"]] == ["F2"]
    assert _dispatch(client, auth, world).status_code == 409             # trip already dispatched


def test_dispatch_rules_and_permissions(client, world, auth, db):
    u = world.users
    assert _dispatch(client, auth, world, user=u.tech1).status_code == 403     # no logistics.operate
    assert _dispatch(client, auth, world, user=u.auditor).status_code == 403
    assert _dispatch(client, auth, world, user=u.op3).status_code == 404       # F1 plan, F3 operator
    assert _dispatch(client, auth, world, vehicle_code="x").status_code == 422
    assert _dispatch(client, auth, world, vehicle_code="KA01; DROP").status_code == 422
    assert _dispatch(client, auth, world, trips=[7]).status_code == 422        # unknown trip
    h = auth(u.admin)
    other = client.post(f"{API}/route-plans", headers=h, json={"incident_id": str(world.excursion.id)}).json()
    r = client.post(f"{API}/route-plans/{other['id']}/dispatch", headers=auth(u.op1), json={"vehicle_code": "KA01"})
    assert r.status_code == 409 and "APPROVED" in r.json()["detail"]          # PROPOSED plans cannot roll


# --------------------------------------------------------------------------- healthy telemetry
def test_valid_reading_updates_position_without_alerts(client, world, auth, db):
    s = _shipment(client, auth, world)
    r = _reading(client, s["id"], temperature=5.2)
    assert r.status_code == 202 and r.json()["alert"] is None and r.json()["sensor_state"] == "OK"
    row = db.get(Shipment, uuid.UUID(s["id"]))
    db.refresh(row)
    assert (row.last_lat, row.last_temperature) == (MIDWAY["lat"], 5.2)
    assert db.query(TransitAlert).count() == 0


# --------------------------------------------------------------------------- sensor failure
def test_logger_fault_alerts_operator_and_nearby_stores(client, world, auth, db):
    s = _shipment(client, auth, world)
    r = _reading(client, s["id"], temperature=None, sensor_status="FAULT")
    assert r.status_code == 202
    alert = r.json()["alert"]
    assert alert["alert_type"] == "SENSOR_FAULT" and alert["severity"] == "HIGH"
    near = alert["nearby"]
    codes = [n["facility_code"] for n in near]
    assert codes[0] == "F2" and near[0]["reachable_within_hold"] is True     # nearest compatible store first
    assert near[0]["distance_km"] < 5 and near[0]["eta_minutes"] <= near[0]["eta_p90_minutes"]
    assert all(u["unit_code"] != "FZ1" for n in near for u in n["units"])    # freezer would freeze Penta
    assert all(u["unit_code"] != "U1" for n in near for u in n["units"])     # never back to the failing unit
    assert "Nearest compatible store: Facility Two" in alert["message"]
    # incident for the source facility
    inc = db.query(Incident).filter(Incident.incident_type == IncidentType.TRANSIT_SENSOR_FAILURE).one()
    assert inc.facility_id == world.f1.id and inc.severity == ViolationSeverity.HIGH
    assert alert["incident_number"] == inc.incident_number
    # vehicle operator (dispatcher), source facility staff and the nearby store's operator are alerted
    assert _notes(db, world.users.op1, "sensor fault in transit") >= 1
    assert _notes(db, world.users.sup1, "sensor fault in transit") >= 1
    assert _notes(db, world.op2, "Incoming diversion possible") == 1
    msg = db.query(Notification).filter(Notification.user_id == world.op2.id,
                                        Notification.title.contains("Incoming")).one().message
    assert "recommended destination" in msg and "U2" in msg
    assert db.get(Shipment, uuid.UUID(s["id"])).sensor_state == TransitSensorState.FAULT
    # repeated faults do not spam: one active alert per failure mode, position refreshed
    _reading(client, s["id"], lat=13.02, lon=77.596, temperature=None, sensor_status="ERROR")
    assert db.query(TransitAlert).filter(TransitAlert.alert_type == TransitAlertType.SENSOR_FAULT).count() == 1
    assert _notes(db, world.op2, "Incoming diversion possible") == 1


def test_implausible_value_is_a_sensor_fault_not_an_excursion(client, world, auth, db):
    s = _shipment(client, auth, world)
    a = _reading(client, s["id"], temperature=150.0).json()["alert"]
    assert a["alert_type"] == "SENSOR_FAULT" and "Implausible" in a["message"]
    assert db.query(Incident).filter(Incident.incident_type == IncidentType.TRANSIT_EXCURSION).count() == 0


def test_cargo_temperature_excursion_in_transit_is_critical(client, world, auth, db):
    s = _shipment(client, auth, world)
    a = _reading(client, s["id"], temperature=11.5).json()["alert"]
    assert a["alert_type"] == "TEMPERATURE_EXCURSION" and a["severity"] == "CRITICAL" and a["temperature"] == 11.5
    assert "+3.5 °C" in a["message"]
    inc = db.query(Incident).filter(Incident.incident_type == IncidentType.TRANSIT_EXCURSION).one()
    assert inc.severity == ViolationSeverity.CRITICAL
    assert db.query(Notification).filter(Notification.user_id == world.users.op1.id,
                                         Notification.level == "CRITICAL").count() >= 1


def test_silent_logger_is_detected_by_the_worker_sweep(client, world, auth, db):
    s = _shipment(client, auth, world)
    row = db.get(Shipment, uuid.UUID(s["id"]))
    row.last_reading_at = datetime.now(timezone.utc) - timedelta(minutes=12)
    row.last_lat, row.last_lon = MIDWAY["lat"], MIDWAY["lon"]
    db.commit()
    assert TransitService.check_offline(db) == {"transit_offline_alerts": 1}
    a = db.query(TransitAlert).one()
    assert a.alert_type == TransitAlertType.SENSOR_OFFLINE and "No data-logger reading for 12 min" in a.message
    assert a.nearby and a.nearby[0]["facility_code"] == "F2"
    db.refresh(row)
    assert row.sensor_state == TransitSensorState.OFFLINE
    assert TransitService.check_offline(db) == {"transit_offline_alerts": 0}   # no duplicate
    # logger comes back: offline alert resolves automatically
    _reading(client, s["id"], temperature=4.9)
    db.refresh(a)
    db.refresh(row)
    assert a.status == TransitAlertStatus.RESOLVED and row.sensor_state == TransitSensorState.OK


def test_worker_job_registered():
    from app.workers.jobs import JOBS
    assert "transit" in [name for name, _, _ in JOBS]


# --------------------------------------------------------------------------- nearby ranking (ML ETA)
def test_nearby_skips_failing_units_and_flags_unreachable_stores(client, world, auth, db):
    s = _shipment(client, auth, world)
    feed(db, "S-U2", [5, 9.8, 9.9, 10.2], start_minutes_ago=4)   # the planned destination fails too
    row = db.get(Shipment, uuid.UUID(s["id"]))
    row.hold_minutes = 600                                        # long hold: reachable at any time of day
    db.commit()
    near = TransitService.nearby_storage(db, row, MIDWAY["lat"], MIDWAY["lon"],
                                         at=datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc))
    assert [n["facility_code"] for n in near] == ["F3"]          # only Mysuru is left
    assert near[0]["distance_km"] > 100 and near[0]["reachable_within_hold"] is True
    row.hold_minutes = 60                                         # a short cold-box hold time
    db.commit()
    a = _reading(client, s["id"], temperature=None, sensor_status="FAULT").json()["alert"]
    assert a["nearby"][0]["reachable_within_hold"] is False
    assert "No compatible store reachable within the remaining hold time" in a["message"]


def test_nearby_respects_free_capacity(client, world, auth, db):
    s = _shipment(client, auth, world)
    world.units.u2.capacity_litres = 1.0          # 1000 doses need 3.5 L
    db.commit()
    row = db.get(Shipment, uuid.UUID(s["id"]))
    assert "F2" not in [n["facility_code"] for n in TransitService.nearby_storage(db, row, 13.0, 77.6)]


def test_nearby_endpoint(client, world, auth):
    s = _shipment(client, auth, world)
    r = client.get(f"{API}/shipments/{s['id']}/nearby", headers=auth(world.users.sup1))
    assert r.status_code == 200 and r.json()[0]["facility_code"] == "F2"
    r = client.get(f"{API}/shipments/{s['id']}/nearby?lat=12.30&lon=76.64", headers=auth(world.users.sup1))
    assert r.json()[0]["facility_code"] == "F3"                    # from Mysuru, Mysuru is nearest


# --------------------------------------------------------------------------- human actions
def test_divert_resolves_alerts_and_tells_the_receiving_store(client, world, auth, db):
    s = _shipment(client, auth, world)
    _reading(client, s["id"], temperature=None, sensor_status="FAULT")
    r = client.post(f"{API}/shipments/{s['id']}/divert", headers=auth(world.users.op1),
                    json={"facility_id": str(world.f2.id), "note": "Driver confirmed, 10 min away"})
    assert r.status_code == 200 and r.json()["status"] == "DIVERTED" and r.json()["diverted_to"] == "Facility Two"
    assert db.query(TransitAlert).filter(TransitAlert.status != TransitAlertStatus.RESOLVED).count() == 0
    assert _notes(db, world.op2, "Diverted shipment arriving") == 1
    assert _reading(client, s["id"], temperature=5).status_code == 409   # closed shipments take no telemetry
    assert client.post(f"{API}/shipments/{s['id']}/deliver", headers=auth(world.users.op1), json={}).status_code == 409


def test_deliver_closes_the_shipment(client, world, auth, db):
    s = _shipment(client, auth, world)
    r = client.post(f"{API}/shipments/{s['id']}/deliver", headers=auth(world.users.op1), json={"note": "Received"})
    assert r.status_code == 200 and r.json()["status"] == "DELIVERED" and r.json()["closed_at"]
    assert client.get(f"{API}/shipments?status=DELIVERED", headers=auth(world.users.admin)).json()[0]["id"] == s["id"]


def test_acknowledge_and_visibility(client, world, auth, db):
    s = _shipment(client, auth, world)
    aid = _reading(client, s["id"], temperature=12.0).json()["alert"]["id"]
    u = world.users
    assert [a["id"] for a in client.get(f"{API}/transit-alerts", headers=auth(u.auditor)).json()] == [aid]
    assert client.get(f"{API}/transit-alerts", headers=auth(u.op3)).json() == []         # other facility
    assert client.get(f"{API}/shipments/{s['id']}", headers=auth(u.op3)).status_code == 404
    assert client.post(f"{API}/transit-alerts/{aid}/acknowledge", headers=auth(u.auditor)).status_code == 403
    r = client.post(f"{API}/transit-alerts/{aid}/acknowledge", headers=auth(u.op1))
    assert r.status_code == 200 and r.json()["status"] == "ACKNOWLEDGED" and r.json()["acknowledged_by_name"] == "op1"
    assert client.post(f"{API}/transit-alerts/{aid}/acknowledge", headers=auth(u.op1)).status_code == 409
    detail = client.get(f"{API}/shipments/{s['id']}", headers=auth(u.sup1)).json()
    assert detail["open_alerts"] == 1 and detail["alerts"][0]["status"] == "ACKNOWLEDGED"


def test_telemetry_authentication(client, world, auth):
    s = _shipment(client, auth, world)
    assert _reading(client, s["id"], headers={}, temperature=5).status_code == 401
    assert _reading(client, s["id"], headers={"X-Ingest-Key": "wrong"}, temperature=5).status_code == 401
    assert _reading(client, s["id"], headers=auth(world.users.tech1), temperature=5).status_code == 403
    assert _reading(client, s["id"], headers=auth(world.users.op3), temperature=5).status_code == 404
    assert _reading(client, s["id"], headers=auth(world.users.op1), temperature=5).status_code == 202
    assert _reading(client, s["id"], lat=95, temperature=5).status_code == 422
    assert client.post(f"{API}/shipments/{uuid.uuid4()}/telemetry", headers=KEY,
                       json={**MIDWAY, "temperature": 5}).status_code == 404
