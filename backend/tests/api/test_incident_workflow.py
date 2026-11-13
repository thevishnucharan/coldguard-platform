"""Full incident lifecycle via the API with separate operator / supervisor identities."""
from datetime import datetime, timedelta, timezone

from app.models import AuditLog, Batch, Incident, IncidentEvent
from app.models.enums import BatchStatus, IncidentStatus, ViolationSeverity
from app.services.escalation import run_escalations
from app.services.inventory import InventoryService
from tests.conftest import feed


def _excursion(db, org, with_batch=True):
    if with_batch:
        b = InventoryService.receive(db, org.users.op1, batch_number="B-EXC", product_id=org.product.id,
                                     storage_unit_id=org.units.u1.id, quantity=100,
                                     expiry_date=datetime.now(timezone.utc) + timedelta(days=200))
        b.start_time = datetime.now(timezone.utc) - timedelta(days=3)
        db.commit()
    feed(db, "S-U1", [5, 9.8, 9.9, 5.0], start_minutes_ago=5)
    return db.query(Incident).one()


def test_full_lifecycle(client, org, db, auth):
    inc = _excursion(db, org)
    base = f"/api/v1/incidents/{inc.id}"
    op, op2, sup = auth(org.users.op1), auth(org.users.op1b), auth(org.users.sup1)

    d = client.get(base, headers=op).json()
    assert d["status"] == "OPEN" and "acknowledge" in d["available_actions"]
    assert d["affected_batch_count"] == 1

    assert client.post(f"{base}/acknowledge", headers=op, json={"notes": "On it"}).json()["status"] == "ACKNOWLEDGED"
    assert client.post(f"{base}/investigate", headers=op, json={"notes": "Door ajar"}).json()["status"] == "INVESTIGATING"
    assert client.post(f"{base}/notes", headers=op, json={"note": "Checked log"}).status_code == 200

    ca = client.post(f"{base}/corrective-actions", headers=op,
                     json={"description": "Replace gasket and retrain staff", "root_cause": "Worn gasket"})
    assert ca.status_code == 201
    ca_id = ca.json()["id"]
    assert client.get(base, headers=op).json()["status"] == "CORRECTIVE_ACTION_PENDING"

    # operator cannot approve; supervisor rejects first, operator revises
    assert client.post(f"{base}/corrective-actions/{ca_id}/review", headers=op,
                       json={"decision": "approve"}).status_code == 403
    r = client.post(f"{base}/corrective-actions/{ca_id}/review", headers=sup,
                    json={"decision": "request_revision", "comment": "Add a door alarm check"})
    assert r.json()["status"] == "REVISION_REQUESTED"
    assert client.get(base, headers=op).json()["status"] == "INVESTIGATING"
    ca2 = client.post(f"{base}/corrective-actions", headers=op,
                      json={"description": "Replace gasket, add door alarm check", "root_cause": "Worn gasket"}).json()
    assert client.post(f"{base}/corrective-actions/{ca2['id']}/review", headers=sup,
                       json={"decision": "approve", "comment": "OK"}).json()["status"] == "APPROVED"

    # cannot verify before implementing
    assert client.post(f"{base}/verify-recovery", headers=op, json={}).status_code == 400
    assert client.post(f"{base}/corrective-actions/{ca2['id']}/implement", headers=op2,
                       json={"notes": "Done"}).json()["status"] == "IMPLEMENTED"
    assert client.post(f"{base}/verify-recovery", headers=op, json={"notes": "Stable"}).json()["status"] == "UNDER_REVIEW"

    # supervisor review -> resolved; closing requires vaccine disposition (batch affected)
    assert client.post(f"{base}/review", headers=op, json={"decision": "resolve"}).status_code == 403
    assert client.post(f"{base}/review", headers=sup, json={"decision": "resolve", "notes": "Good"}).json()["status"] == "RESOLVED"
    assert client.post(f"{base}/close", headers=sup, json={"closure_evidence": "x"}).status_code == 400
    r = client.post(f"{base}/close", headers=sup, json={"closure_evidence": "Data logger reviewed",
                                                        "vaccine_disposition": "Stability data reviewed; batch usable"})
    assert r.status_code == 200 and r.json()["status"] == "CLOSED"

    # timeline captured every step, immutably
    events = [e["event_type"] for e in client.get(f"{base}/events", headers=sup).json()]
    for e in ("DETECTED", "OPENED", "ACKNOWLEDGED", "INVESTIGATION_STARTED", "CORRECTIVE_ACTION_PROPOSED",
              "FURTHER_INVESTIGATION_REQUESTED", "CORRECTIVE_ACTION_APPROVED", "CORRECTIVE_ACTION_IMPLEMENTED",
              "RECOVERY_VERIFIED", "RESOLVED", "CLOSED"):
        assert e in events, e
    assert db.query(AuditLog).filter(AuditLog.action == "CLOSED").count() == 1
    # batch status never changed automatically
    assert db.query(Batch).one().status == BatchStatus.ACTIVE


def test_invalid_transitions_and_roles(client, org, db, auth):
    inc = _excursion(db, org, with_batch=False)
    base = f"/api/v1/incidents/{inc.id}"
    assert client.post(f"{base}/investigate", headers=auth(org.users.op1), json={}).status_code == 400  # not acked
    assert client.post(f"{base}/acknowledge", headers=auth(org.users.admin), json={}).status_code == 403
    assert client.post(f"{base}/acknowledge", headers=auth(org.users.auditor), json={}).status_code == 403
    assert client.post(f"{base}/close", headers=auth(org.users.sup1), json={}).status_code == 400  # not resolved
    assert client.post(f"{base}/close", headers=auth(org.users.op1),
                       json={"false_alarm": True, "closure_evidence": "x"}).status_code == 403


def test_false_alarm_closure_requires_justification(client, org, db, auth):
    inc = _excursion(db, org, with_batch=False)
    base = f"/api/v1/incidents/{inc.id}"
    sup = auth(org.users.sup1)
    assert client.post(f"{base}/close", headers=sup, json={"false_alarm": True}).status_code == 400
    r = client.post(f"{base}/close", headers=sup, json={"false_alarm": True, "closure_evidence": "Probe in door test"})
    assert r.json()["status"] == "CLOSED" and r.json()["review_decision"] == "FALSE_ALARM"


def test_supervisor_cannot_review_own_proposal(db, org):
    import pytest
    from fastapi import HTTPException
    from app.services.incident import IncidentService
    inc = _excursion(db, org, with_batch=False)

    class A:
        notes = None
    IncidentService.acknowledge(db, inc.id, org.users.op1, A())
    IncidentService.investigate(db, inc.id, org.users.op1, A())
    ca = IncidentService.propose_corrective_action(db, inc.id, org.users.sup1, description="Self-proposed fix",
                                                   root_cause=None)
    with pytest.raises(HTTPException) as e:
        IncidentService.review_corrective_action(db, inc.id, ca.id, org.users.sup1, "approve", None)
    assert e.value.status_code == 403


def test_assign_only_to_operator_in_scope(client, org, db, auth):
    inc = _excursion(db, org, with_batch=False)
    base = f"/api/v1/incidents/{inc.id}/assign"
    sup = auth(org.users.sup1)
    assert client.post(base, headers=sup, json={"assignee_id": str(org.users.op3.id)}).status_code == 400
    assert client.post(base, headers=sup, json={"assignee_id": str(org.users.tech1.id)}).status_code == 400
    assert client.post(base, headers=sup, json={"assignee_id": str(org.users.op1b.id)}).json()["assignee_name"] == "op1b"


def test_escalation_rules_run_in_background(db, org):
    feed(db, "S-U1", [5, 13.0], start_minutes_ago=2)
    inc = db.query(Incident).one()
    assert inc.severity == ViolationSeverity.CRITICAL
    later = datetime.now(timezone.utc) + timedelta(minutes=20)
    assert run_escalations(db, now=later)["UNACK_CRITICAL"] == 1
    assert run_escalations(db, now=later)["UNACK_CRITICAL"] == 0  # not repeated
    db.refresh(inc)
    assert inc.escalation_level == 1
    assert db.query(IncidentEvent).filter_by(incident_id=inc.id, event_type="ESCALATED").count() == 1
    much_later = datetime.now(timezone.utc) + timedelta(hours=30)
    assert run_escalations(db, now=much_later)["LONG_RUNNING"] == 1


def test_manual_escalation_and_listing_filters(client, org, db, auth):
    inc = _excursion(db, org, with_batch=False)
    r = client.post(f"/api/v1/incidents/{inc.id}/escalate", headers=auth(org.users.op1), json={"reason": "Need help"})
    assert r.json()["escalation_level"] == 1
    lst = client.get("/api/v1/incidents?escalated=true&active=true", headers=auth(org.users.sup1)).json()
    assert lst["total"] == 1
    assert client.get("/api/v1/incidents?status=CLOSED", headers=auth(org.users.sup1)).json()["total"] == 0


def test_evidence_and_affected_batches_read_only_for_auditor(client, org, db, auth):
    inc = _excursion(db, org)
    h = auth(org.users.auditor)
    ev = client.get(f"/api/v1/incidents/{inc.id}/evidence", headers=h).json()
    assert ev["max_limit"] == 8 and len(ev["points"]) == 4
    assert len(client.get(f"/api/v1/incidents/{inc.id}/affected-batches", headers=h).json()) == 1
    assert client.get(f"/api/v1/incidents/{inc.id}", headers=h).json()["available_actions"] == []


def test_operator_can_report_equipment_incident(client, org, auth):
    r = client.post("/api/v1/incidents", headers=auth(org.users.op1), json={
        "storage_unit_id": str(org.units.u1.id), "title": "Compressor noisy", "description": "Loud rattle"})
    assert r.status_code == 201 and r.json()["source"] == "MANUAL" and r.json()["status"] == "OPEN"
    r = client.post("/api/v1/incidents", headers=auth(org.users.op1), json={
        "storage_unit_id": str(org.units.u3.id), "title": "Other facility", "description": "nope nope"})
    assert r.status_code == 404


_ = IncidentStatus
