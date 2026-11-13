"""Batch traceability, FEFO, ledger immutability and authorised disposition."""
from datetime import datetime, timedelta, timezone

import pytest

from app.db.immutability import ImmutableRecordError
from app.models import Batch, InventoryMovement
from app.models.enums import BatchStatus, MovementType
from app.services.inventory import InventoryService


def _recv(client, h, org, number, qty=100, days=100, unit=None):
    return client.post("/api/v1/batches/receive", headers=h, json={
        "batch_number": number, "product_id": str(org.product.id), "storage_unit_id": str((unit or org.units.u1).id),
        "quantity": qty, "expiry_date": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(),
        "supplier": "State store"})


def test_receive_creates_batch_and_receipt_movement(client, org, auth, db):
    r = _recv(client, auth(org.users.op1), org, "B-1", qty=250)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["current_quantity"] == 250 and b["quantity_received"] == 250 and b["facility_id"] == str(org.f1.id)
    m = db.query(InventoryMovement).one()
    assert m.movement_type == MovementType.RECEIPT and m.quantity_after == 250 and m.performed_by_name == "op1"


def test_receive_validations(client, org, auth):
    h = auth(org.users.op1)
    assert _recv(client, h, org, "B-1").status_code == 201
    assert _recv(client, h, org, "B-1").status_code == 409                    # duplicate batch number
    assert _recv(client, h, org, "B-2", days=-1).status_code == 400            # already expired
    assert _recv(client, h, org, "B-3", qty=0).status_code == 422
    assert _recv(client, h, org, "B-4", unit=org.units.fz1).status_code == 400  # 2-8 product into a freezer


def test_fefo_order_enforcement_and_override(client, org, auth):
    h = auth(org.users.op1)
    late = _recv(client, h, org, "LATE", days=300).json()
    early = _recv(client, h, org, "EARLY", days=40).json()
    q = client.get(f"/api/v1/inventory/fefo?product_id={org.product.id}&facility_id={org.f1.id}", headers=h).json()
    assert [b["batch_number"] for b in q] == ["EARLY", "LATE"]
    r = client.post(f"/api/v1/batches/{late['id']}/issue", headers=h, json={"quantity": 10})
    assert r.status_code == 409 and "FEFO" in r.json()["detail"]
    r = client.post(f"/api/v1/batches/{late['id']}/issue", headers=h,
                    json={"quantity": 10, "override_fefo_reason": "Outreach session needs 10-dose vials"})
    assert r.status_code == 200 and r.json()["current_quantity"] == 90
    assert client.post(f"/api/v1/batches/{early['id']}/issue", headers=h, json={"quantity": 5}).status_code == 200


def test_issue_fefo_allocates_across_batches_atomically(client, org, auth, db):
    h = auth(org.users.op1)
    assert _recv(client, h, org, "AA", qty=30, days=20).status_code == 201
    assert _recv(client, h, org, "BB", qty=50, days=60).status_code == 201
    body = {"product_id": str(org.product.id), "facility_id": str(org.f1.id), "quantity": 45, "reason": "Session"}
    r = client.post("/api/v1/inventory/issue-fefo", headers=h, json=body)
    assert r.status_code == 200
    assert [(m["batch_number"], m["quantity_change"]) for m in r.json()] == [("AA", -30), ("BB", -15)]
    a = db.query(Batch).filter_by(batch_number="AA").one()
    assert a.current_quantity == 0 and a.status == BatchStatus.DEPLETED
    body["quantity"] = 1000
    before = db.query(InventoryMovement).count()
    assert client.post("/api/v1/inventory/issue-fefo", headers=h, json=body).status_code == 400
    assert db.query(InventoryMovement).count() == before  # nothing partially written


def test_quarantine_release_requires_supervisor(client, org, auth):
    op, sup, tech = auth(org.users.op1), auth(org.users.sup1), auth(org.users.tech1)
    b = _recv(client, op, org, "Q-1").json()
    base = f"/api/v1/batches/{b['id']}"
    assert client.post(f"{base}/quarantine", headers=tech, json={"reason": "excursion"}).status_code == 403
    assert client.post(f"{base}/quarantine", headers=op, json={"reason": "Excursion INC-1"}).json()["status"] == "QUARANTINED"
    assert client.post(f"{base}/issue", headers=op, json={"quantity": 1}).status_code == 400
    assert client.post(f"{base}/release", headers=op, json={"reason": "Looks fine to me"}).status_code == 403
    assert client.post(f"{base}/release", headers=auth(org.users.admin), json={"reason": "admin release"}).status_code == 403
    assert client.post(f"{base}/release", headers=sup, json={"reason": "short"}).status_code == 400
    r = client.post(f"{base}/release", headers=sup, json={"reason": "Manufacturer stability data reviewed"})
    assert r.json()["status"] == "ACTIVE"
    detail = client.get(base, headers=sup).json()
    assert [m["movement_type"] for m in detail["movements"]] == ["RECEIPT", "QUARANTINE", "RELEASE"]


def test_disposal(client, org, auth):
    op, sup = auth(org.users.op1), auth(org.users.sup1)
    b = _recv(client, op, org, "D-1").json()
    base = f"/api/v1/batches/{b['id']}"
    assert client.post(f"{base}/dispose", headers=sup, json={"reason": "Not quarantined yet"}).status_code == 400
    client.post(f"{base}/quarantine", headers=op, json={"reason": "Frozen"})
    assert client.post(f"{base}/dispose", headers=op, json={"reason": "Freeze damage confirmed"}).status_code == 403
    r = client.post(f"{base}/dispose", headers=sup, json={"reason": "Freeze damage confirmed by shake test"})
    assert r.json()["status"] == "DISCARDED" and r.json()["current_quantity"] == 0


def test_transfer_adjust_reconcile_ledger(client, org, auth, db):
    op = auth(org.users.op1)
    b = _recv(client, op, org, "T-1", qty=100).json()
    base = f"/api/v1/batches/{b['id']}"
    # u2 is in F2 which op1 is not assigned to
    assert client.post(f"{base}/transfer", headers=op, json={"to_storage_unit_id": str(org.units.u2.id)}).status_code == 404
    assert client.post(f"{base}/adjust", headers=op, json={"change": -3, "reason": "Broken vials"}).json()["current_quantity"] == 97
    assert client.post(f"{base}/adjust", headers=op, json={"change": -500, "reason": "oops"}).status_code == 400
    assert client.post(f"{base}/reconcile", headers=op, json={"counted_quantity": 95}).json()["current_quantity"] == 95
    moves = db.query(InventoryMovement).order_by(InventoryMovement.created_at).all()
    running = 0
    for m in moves:
        running += m.quantity_change
        assert m.quantity_after == running  # ledger is internally consistent


def test_ledger_is_immutable(db, org):
    b = InventoryService.receive(db, org.users.op1, batch_number="IM-1", product_id=org.product.id,
                                 storage_unit_id=org.units.u1.id, quantity=10,
                                 expiry_date=datetime.now(timezone.utc) + timedelta(days=30))
    m = db.query(InventoryMovement).filter_by(batch_id=b.id).one()
    m.quantity_change = 999
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()
    db.delete(db.query(InventoryMovement).one())
    with pytest.raises(ImmutableRecordError):
        db.commit()


def test_expired_stock_marked_by_job(db, org):
    b = InventoryService.receive(db, org.users.op1, batch_number="EXP-1", product_id=org.product.id,
                                 storage_unit_id=org.units.u1.id, quantity=10,
                                 expiry_date=datetime.now(timezone.utc) + timedelta(days=1))
    b.expiry_date = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    assert InventoryService.mark_expired(db) == 1
    db.refresh(b)
    assert b.status == BatchStatus.EXPIRED


def test_technician_cannot_touch_stock(client, org, auth):
    b = _recv(client, auth(org.users.op1), org, "TECH-1").json()
    h = auth(org.users.tech1)
    assert client.get(f"/api/v1/batches/{b['id']}", headers=h).status_code == 403  # no inventory.view at all
    assert client.post(f"/api/v1/batches/{b['id']}/adjust", headers=h, json={"change": 1, "reason": "x y z"}).status_code == 403
