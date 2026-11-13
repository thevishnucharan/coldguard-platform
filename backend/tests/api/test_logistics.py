"""Excursion relocation routing through the API: real excursion pipeline, real ML ETA model,
RBAC + facility scope, persistence, approval workflow, audit and notifications."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import AuditLog, Batch, Incident, Notification, RoutePlan, UserRoleAssignment
from app.models.enums import BatchStatus, IncidentType, RoutePlanStatus
from app.services.inventory import InventoryService
from tests.conftest import feed

API = "/api/v1/logistics"


@pytest.fixture
def geo(org, db):
    """F1 & F2 are ~7 km apart in Bengaluru (region R1); F3 is Mysuru (~127 km, region R2)."""
    org.f1.latitude, org.f1.longitude = 12.9716, 77.5946
    org.f2.latitude, org.f2.longitude = 13.0350, 77.5970
    org.f3.latitude, org.f3.longitude = 12.2958, 76.6394
    db.commit()
    return org


def _stock(db, org, number, qty, product=None, unit=None):
    b = InventoryService.receive(db, org.users.op1, batch_number=number, product_id=(product or org.product).id,
                                 storage_unit_id=(unit or org.units.u1).id, quantity=qty,
                                 expiry_date=datetime.now(timezone.utc) + timedelta(days=200))
    b.start_time = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    return b


def _excursion(db, sensor="S-U1"):
    feed(db, sensor, [5, 9.8, 9.9, 10.2], start_minutes_ago=5)
    return (db.query(Incident).filter(Incident.incident_type == IncidentType.TEMPERATURE_EXCURSION)
            .order_by(Incident.created_at.desc()).first())


def _plan(client, auth, user, **body):
    return client.post(f"{API}/route-plans", headers=auth(user), json=body)


def _deliveries(plan):
    out = {}
    for t in plan["trips"]:
        for st in t["stops"]:
            for d in st["deliveries"]:
                for b in d["batches"]:
                    out[b["batch_number"]] = (d["unit_code"], st["facility_code"])
    for d in plan["on_site_moves"]:
        for b in d["batches"]:
            out[b["batch_number"]] = (d["unit_code"], "ON_SITE")
    return out


def test_admin_plans_relocation_for_active_excursion(client, geo, db, auth):
    _stock(db, geo, "PENTA-1", 2000)
    _stock(db, geo, "OPV-1", 500, product=geo.frozen)
    inc = _excursion(db)
    admin = geo.users.admin

    exc = client.get(f"{API}/excursions", headers=auth(admin)).json()
    assert [e["incident_number"] for e in exc] == [inc.incident_number]
    assert exc[0]["doses_at_risk"] == 2500 and exc[0]["batches_at_risk"] == 2 and exc[0]["latest_plan"] is None

    r = _plan(client, auth, admin, incident_id=str(inc.id))
    assert r.status_code == 201, r.text
    plan = r.json()
    assert plan["status"] == "PROPOSED" and plan["plan_number"].startswith("RP-")
    assert plan["model"]["available"] is True and plan["model"]["version"].startswith("route-eta-gbr")
    # Penta (2–8 °C only) goes to the nearest healthy fridge (U2 at F2); OPV can sit in the
    # freezer in the same facility (no vehicle needed)
    assert _deliveries(plan) == {"PENTA-1": ("U2", "F2"), "OPV-1": ("FZ1", "ON_SITE")}
    trip = plan["trips"][0]
    stop = trip["stops"][0]
    assert 7 < stop["leg_distance_km"] < 8
    assert 8 <= stop["leg_eta_minutes"] <= stop["leg_eta_p90_minutes"] < 60
    assert plan["summary"]["relocated_doses"] == 2500 and plan["summary"]["unassigned_doses"] == 0
    assert plan["source"]["unit_code"] == "U1"

    row = db.get(RoutePlan, uuid.UUID(plan["id"]))
    assert row.incident_id == inc.id and row.status == RoutePlanStatus.PROPOSED and row.trip_count == 1
    assert db.query(AuditLog).filter(AuditLog.action == "ROUTE_PLAN_CREATED").count() == 1
    assert client.get(f"{API}/excursions", headers=auth(admin)).json()[0]["latest_plan"]["id"] == plan["id"]
    # the plan never moves stock by itself
    assert {b.storage_unit_id for b in db.query(Batch)} == {geo.units.u1.id}


def test_units_with_active_incidents_are_excluded(client, geo, db, auth):
    _stock(db, geo, "PENTA-1", 1000)
    inc = _excursion(db)
    _excursion(db, "S-U2")  # the nearest alternative is failing too
    plan = _plan(client, auth, geo.users.admin, incident_id=str(inc.id)).json()
    assert _deliveries(plan) == {"PENTA-1": ("U3", "F3")}  # falls back to Mysuru
    assert {"unit_code": "U2", "facility_code": "F2",
            "reason": "Unit has an active excursion / equipment / connectivity incident"} in plan["excluded_units"]
    assert plan["trips"][0]["stops"][0]["leg_distance_km"] > 100


def test_hold_time_limits_destinations(client, geo, db, auth):
    _stock(db, geo, "PENTA-1", 1000)
    inc = _excursion(db)
    _excursion(db, "S-U2")
    plan = _plan(client, auth, geo.users.admin, incident_id=str(inc.id), max_trip_minutes=60).json()
    assert plan["trips"] == []
    assert plan["unassigned"][0]["reason"].startswith("Compatible units are beyond the cold-box hold time")
    assert plan["summary"]["unassigned_doses"] == 1000


def test_preview_without_persisting(client, geo, db, auth):
    _stock(db, geo, "PENTA-1", 100)
    r = _plan(client, auth, geo.users.admin, storage_unit_id=str(geo.units.u1.id), persist=False)
    assert r.status_code == 201 and "id" not in r.json()
    assert db.query(RoutePlan).count() == 0


def test_request_validation(client, geo, db, auth):
    h = geo.users.admin
    _stock(db, geo, "PENTA-1", 100)
    inc = _excursion(db)
    assert _plan(client, auth, h).status_code == 422
    assert _plan(client, auth, h, incident_id=str(inc.id), storage_unit_id=str(geo.units.u1.id)).status_code == 422
    assert _plan(client, auth, h, incident_id=str(inc.id), vehicles=0).status_code == 422
    assert _plan(client, auth, h, incident_id=str(inc.id), max_trip_minutes=5).status_code == 422
    assert _plan(client, auth, h, storage_unit_id=str(geo.units.u2.id)).status_code == 409  # nothing to move
    geo.f1.latitude = None
    db.commit()
    assert _plan(client, auth, h, incident_id=str(inc.id)).status_code == 400


def test_non_excursion_incident_is_rejected(client, geo, db, auth):
    from app.models.enums import ViolationSeverity
    from app.services.incident import IncidentService
    inc, _ = IncidentService.open_incident(db, incident_type=IncidentType.EQUIPMENT_FAILURE,
                                           severity=ViolationSeverity.HIGH, facility_id=geo.f1.id,
                                           storage_unit_id=geo.units.u1.id, title="Compressor noise")
    assert _plan(client, auth, geo.users.admin, incident_id=str(inc.id)).status_code == 400


def test_permissions_and_facility_scope(client, geo, db, auth):
    _stock(db, geo, "PENTA-1", 100)
    inc = _excursion(db)
    u = geo.users
    for who in (u.op1, u.sup1, u.tech1, u.auditor):
        assert _plan(client, auth, who, incident_id=str(inc.id)).status_code == 403
    plan = _plan(client, auth, u.admin, incident_id=str(inc.id)).json()
    pid = plan["id"]
    for who in (u.op1, u.sup1, u.auditor):
        assert client.get(f"{API}/route-plans/{pid}", headers=auth(who)).status_code == 200
    assert client.get(f"{API}/route-plans/{pid}", headers=auth(u.tech1)).status_code == 403  # no logistics.view
    # out-of-scope users get 404 (no ID enumeration) and an empty list
    assert client.get(f"{API}/route-plans/{pid}", headers=auth(u.sup2)).status_code == 404
    assert client.get(f"{API}/route-plans", headers=auth(u.op3)).json() == []
    assert client.get(f"{API}/excursions", headers=auth(u.op3)).json() == []
    for who in (u.op1, u.sup1, u.auditor):
        assert client.post(f"{API}/route-plans/{pid}/approve", headers=auth(who), json={}).status_code == 403


def test_approval_workflow_notifies_and_audits(client, geo, db, auth):
    _stock(db, geo, "PENTA-1", 1000)
    inc = _excursion(db)
    h = auth(geo.users.admin)
    p1 = _plan(client, auth, geo.users.admin, incident_id=str(inc.id)).json()
    p2 = _plan(client, auth, geo.users.admin, incident_id=str(inc.id), vehicles=2).json()

    assert client.post(f"{API}/route-plans/{p1['id']}/cancel", headers=h, json={"note": "no"}).status_code == 400
    before = db.query(Notification).filter(Notification.user_id == geo.users.op1.id).count()
    r = client.post(f"{API}/route-plans/{p1['id']}/approve", headers=h, json={"note": "Van KA-01 dispatched"})
    assert r.status_code == 200 and r.json()["status"] == "APPROVED" and r.json()["decided_by_name"] == "admin"
    assert db.query(Notification).filter(Notification.user_id == geo.users.op1.id).count() == before + 1
    assert db.query(Notification).filter(Notification.user_id == geo.users.sup1.id,
                                         Notification.category == "LOGISTICS").count() >= 1

    assert client.post(f"{API}/route-plans/{p1['id']}/approve", headers=h, json={}).status_code == 409  # decided
    assert client.post(f"{API}/route-plans/{p2['id']}/approve", headers=h, json={}).status_code == 409  # one at a time
    r = client.post(f"{API}/route-plans/{p2['id']}/cancel", headers=h, json={"note": "Superseded by approved plan"})
    assert r.json()["status"] == "CANCELLED"

    assert [p["status"] for p in client.get(f"{API}/route-plans?status=APPROVED", headers=h).json()] == ["APPROVED"]
    assert len(client.get(f"{API}/route-plans?incident_id={inc.id}", headers=h).json()) == 2
    actions = {a for (a,) in db.query(AuditLog.action).filter(AuditLog.category == "LOGISTICS")}
    assert actions == {"ROUTE_PLAN_CREATED", "ROUTE_PLAN_APPROVED", "ROUTE_PLAN_CANCELLED"}
    # approval is a recorded decision; stock still only moves through the inventory ledger
    b = db.query(Batch).one()
    assert b.storage_unit_id == geo.units.u1.id and b.status == BatchStatus.ACTIVE


def test_approved_plan_is_executable_through_the_inventory_ledger(client, geo, db, auth):
    """Executing a plan uses the normal transfer endpoint: it needs inventory.manage AND scope over
    the receiving facility (here op1 is also assigned to F2). Supervisors cannot move stock."""
    b = _stock(db, geo, "PENTA-1", 100)
    inc = _excursion(db)
    plan = _plan(client, auth, geo.users.admin, incident_id=str(inc.id)).json()
    client.post(f"{API}/route-plans/{plan['id']}/approve", headers=auth(geo.users.admin), json={})
    unit_id = plan["trips"][0]["stops"][0]["deliveries"][0]["storage_unit_id"]
    assert unit_id == str(geo.units.u2.id)
    body = {"to_storage_unit_id": unit_id, "reason": f"Excursion relocation {plan['plan_number']}"}
    assert client.post(f"/api/v1/batches/{b.id}/transfer", headers=auth(geo.users.sup1), json=body).status_code == 403
    assert client.post(f"/api/v1/batches/{b.id}/transfer", headers=auth(geo.users.op1), json=body).status_code == 404
    db.add(UserRoleAssignment(user_id=geo.users.op1.id, role=geo.users.op1.role, facility_id=geo.f2.id))
    db.commit()
    r = client.post(f"/api/v1/batches/{b.id}/transfer", headers=auth(geo.users.op1), json=body)
    assert r.status_code == 200, r.text
    db.refresh(b)
    assert b.storage_unit_id == geo.units.u2.id and b.facility_id == geo.f2.id


def test_model_endpoint(client, geo, auth):
    info = client.get(f"{API}/model", headers=auth(geo.users.auditor)).json()
    assert info["available"] is True and "p50_mae_minutes" in info["metrics"]
    assert client.get(f"{API}/model", headers=auth(geo.users.tech1)).status_code == 403
