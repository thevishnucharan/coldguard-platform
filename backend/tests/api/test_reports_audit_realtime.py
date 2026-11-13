"""Report authorisation/scoping, audit trail, notifications, WebSocket scoping, metrics."""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from app.db.immutability import ImmutableRecordError
from app.models import AuditLog
from app.services.audit import log_audit
from app.services.inventory import InventoryService
from tests.conftest import feed


def _stock(db, org):
    for unit, user, n in ((org.units.u1, org.users.op1, "R-F1"), (org.units.u3, org.users.op3, "R-F3")):
        InventoryService.receive(db, user, batch_number=n, product_id=org.product.id, storage_unit_id=unit.id,
                                 quantity=10, expiry_date=datetime.now(timezone.utc) + timedelta(days=90))


def test_report_types_depend_on_permissions(client, org, auth):
    tech = {r["key"] for r in client.get("/api/v1/reports/types", headers=auth(org.users.tech1)).json()["reports"]}
    assert "maintenance" in tech and "stock" not in tech and "audit" not in tech
    aud = {r["key"] for r in client.get("/api/v1/reports/types", headers=auth(org.users.auditor)).json()["reports"]}
    assert {"audit", "stock", "temperature", "incidents"} <= aud


def test_csv_export_is_scoped_to_facility(client, org, auth, db):
    _stock(db, org)
    r = client.get("/api/v1/reports/export?type=stock&format=csv", headers=auth(org.users.op1))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    text = r.content.decode()
    assert "R-F1" in text and "R-F3" not in text
    assert client.get("/api/v1/reports/export?type=stock&format=csv", headers=auth(org.users.auditor)).content.decode().count("R-F") == 2
    assert db.query(AuditLog).filter(AuditLog.action == "REPORT_EXPORTED").count() == 2


def test_export_forbidden_and_cross_facility_denied(client, org, auth):
    assert client.get("/api/v1/reports/export?type=audit", headers=auth(org.users.op1)).status_code == 403
    assert client.get(f"/api/v1/reports/export?type=stock&facility_id={org.f3.id}",
                      headers=auth(org.users.op1)).status_code == 403
    assert client.get("/api/v1/reports/export?type=nope", headers=auth(org.users.op1)).status_code == 404


def test_pdf_export_and_temperature_report(client, org, auth, db):
    feed(db, "S-U1", [5, 5.2, 5.1], start_minutes_ago=3)
    r = client.get("/api/v1/reports/export?type=temperature&format=pdf&days=1", headers=auth(org.users.sup1))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_csv_injection_sanitised():
    from app.services.reporting import ReportingService
    out = ReportingService.to_csv("t", ["a"], [["=HYPERLINK(\"x\")"], ["+1"], ["ok"]], {}).decode()
    rows = list(csv.reader(io.StringIO(out)))
    assert ["'=HYPERLINK(\"x\")"] in rows and ["'+1"] in rows and ["ok"] in rows


def test_audit_log_is_append_only(db, org):
    entry = log_audit(db, org.users.admin, "X", "Thing", None, {"password": "secret", "ok": 1})
    assert entry.details["password"] == "***" and entry.details["ok"] == 1
    entry.action = "TAMPERED"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()


def test_sensitive_operations_are_audited(client, org, auth, db):
    client.post("/api/v1/users", headers=auth(org.users.admin), json={
        "name": "Aud Test", "email": "a2@t.io", "password": "Abcdefgh1234", "role": "AUDITOR"})
    client.put("/api/v1/system/escalation-rules", headers=auth(org.users.admin), json={"max_level": 4})
    actions = {a.action for a in db.query(AuditLog)}
    assert {"USER_CREATED", "ESCALATION_RULES_UPDATED"} <= actions
    r = client.get("/api/v1/audit-logs?category=SECURITY", headers=auth(org.users.auditor)).json()
    assert r["total"] >= 1
    assert all(i["category"] == "SECURITY" for i in r["items"])


def test_notifications_flow(client, org, auth, db):
    feed(db, "S-U1", [5, 13.0], start_minutes_ago=2)
    h = auth(org.users.op1)
    n = client.get("/api/v1/notifications", headers=h).json()
    assert n["unread"] >= 1 and n["items"][0]["link"].startswith("/incidents/")
    assert client.post("/api/v1/notifications/read-all", headers=h).status_code == 204
    assert client.get("/api/v1/notifications", headers=h).json()["unread"] == 0


def test_websocket_requires_auth_and_filters_by_scope(client, org, auth, db):
    from app.services.realtime import hub
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_text('{"token":"bad"}')
        with pytest.raises(Exception):
            ws.receive_json()
    token = auth(org.users.op1)["Authorization"].split()[1]
    with client.websocket_connect("/api/v1/ws") as ws:
        ws.send_text('{"token":"%s"}' % token)
        assert ws.receive_json()["type"] == "hello"
        hub.publish("reading", {"v": "other"}, facility_id=org.f3.id)       # filtered out
        hub.publish("reading", {"v": "mine"}, facility_id=org.f1.id)
        hub.publish("notification", {"v": "not-for-me"}, user_ids=[org.users.op3.id])
        hub.publish("notification", {"v": "for-me"}, user_ids=[org.users.op1.id])
        got = [ws.receive_json()["data"]["v"], ws.receive_json()["data"]["v"]]
        assert got == ["mine", "for-me"]


def test_metrics_and_probes(client):
    assert client.get("/health").json()["status"] == "healthy"
    assert client.get("/ready").json()["status"] == "ready"
    client.get("/api/v1/auth/me")
    m = client.get("/metrics").text
    assert "coldguard_http_requests_total" in m and 'route="/api/v1/auth/me"' in m
    assert "coldguard_telemetry_received_total" in m


def test_system_status_admin_only(client, org, auth):
    s = client.get("/api/v1/system/status", headers=auth(org.users.admin)).json()
    assert s["database"] == "ok" and s["ml"]["available"] is True
    assert client.get("/api/v1/system/status", headers=auth(org.users.op1)).status_code == 403


def test_api_datetimes_are_timezone_aware(client, org, auth, db):
    """Regression: SQLite naive datetimes were serialised without offset and shown in local time."""
    feed(db, "S-U1", [5.0], start_minutes_ago=1)
    units = client.get("/api/v1/monitoring/live", headers=auth(org.users.op1)).json()["units"]
    ts = next(u for u in units if u["unit_code"] == "U1")["last_reading_at"]
    assert ts.endswith("Z") or "+00:00" in ts
