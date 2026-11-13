"""Permission matrix + vertical privilege escalation. Every protected endpoint is checked
server-side; these tests call the API directly (no UI involved)."""
import pytest

from app.core.permissions import PERMISSIONS, ROLE_PERMISSIONS, role_has
from app.models.enums import Role


def test_matrix_only_uses_known_permissions():
    for role, perms in ROLE_PERMISSIONS.items():
        assert perms <= set(PERMISSIONS), role


@pytest.mark.parametrize("role,perm,expected", [
    (Role.ADMIN, "incidents.acknowledge", False),       # admin does no routine facility ops
    (Role.ADMIN, "inventory.manage", False),
    (Role.ADMIN, "batches.release", False),            # no clinical disposition authority
    (Role.ADMIN, "maintenance.update", False),
    (Role.ADMIN, "platform.configure", True),
    (Role.OPERATOR, "batches.release", False),
    (Role.OPERATOR, "users.create", False),
    (Role.OPERATOR, "platform.configure", False),
    (Role.OPERATOR, "inventory.manage", True),
    (Role.SUPERVISOR, "corrective_actions.approve", True),
    (Role.SUPERVISOR, "devices.register", False),
    (Role.SUPERVISOR, "platform.configure", False),
    (Role.TECHNICIAN, "inventory.manage", False),
    (Role.TECHNICIAN, "batches.release", False),
    (Role.TECHNICIAN, "calibration.record", True),
    (Role.AUDITOR, "audit.view", True),
])
def test_role_permission_expectations(role, perm, expected):
    assert role_has(role, perm) is expected


def test_auditor_is_read_only():
    writes = {p for p in ROLE_PERMISSIONS[Role.AUDITOR]
              if not p.endswith((".view",)) and p not in ("reports.export",)}
    assert writes == set(), writes


# (user, method, path, body) -> expected status for clearly unauthorised calls
DENIED = [
    ("op1", "GET", "/api/v1/users", None),
    ("op1", "POST", "/api/v1/users", {"name": "x y", "email": "e@t.io", "password": "Abcdefgh1234", "role": "ADMIN"}),
    ("op1", "GET", "/api/v1/dashboards/admin", None),
    ("op1", "PUT", "/api/v1/system/escalation-rules", {"max_level": 5}),
    ("op1", "POST", "/api/v1/sensors", {"sensor_code": "S-NEW", "storage_unit_id": "00000000-0000-0000-0000-000000000000"}),
    ("tech1", "POST", "/api/v1/batches/receive", {"batch_number": "B1", "product_id": "00000000-0000-0000-0000-000000000000",
                                                   "storage_unit_id": "00000000-0000-0000-0000-000000000000",
                                                   "quantity": 1, "expiry_date": "2030-01-01T00:00:00Z"}),
    ("tech1", "GET", "/api/v1/audit-logs", None),
    ("auditor", "POST", "/api/v1/maintenance/tickets", {"facility_id": "00000000-0000-0000-0000-000000000000",
                                                         "title": "xxxxx", "description": "yyyyy"}),
    ("auditor", "POST", "/api/v1/demo/simulation/start", {}),
    ("sup1", "POST", "/api/v1/policies", {"name": "p", "min_temperature": 1, "max_temperature": 2}),
    ("admin", "POST", "/api/v1/batches/receive", {"batch_number": "B1", "product_id": "00000000-0000-0000-0000-000000000000",
                                                   "storage_unit_id": "00000000-0000-0000-0000-000000000000",
                                                   "quantity": 1, "expiry_date": "2030-01-01T00:00:00Z"}),
    ("admin", "GET", "/api/v1/dashboards/technician", None),
    ("tech1", "GET", "/api/v1/dashboards/supervisor", None),
    ("sup1", "GET", "/api/v1/dashboards/operator", None),
]


@pytest.mark.parametrize("who,method,path,body", DENIED)
def test_denied(client, org, auth, who, method, path, body):
    r = client.request(method, path, headers=auth(getattr(org.users, who)), json=body)
    assert r.status_code == 403, (who, path, r.status_code, r.text)


def test_denials_are_audited(client, org, auth, db):
    from app.models import AuditLog
    client.get("/api/v1/users", headers=auth(org.users.op1))
    assert db.query(AuditLog).filter(AuditLog.action == "PERMISSION_DENIED").count() == 1


def test_operator_cannot_escalate_own_role(client, org, auth):
    r = client.put(f"/api/v1/users/{org.users.op1.id}", headers=auth(org.users.op1), json={"role": "ADMIN"})
    assert r.status_code == 403


def test_admin_cannot_change_own_role_or_deactivate_self(client, org, auth):
    h = auth(org.users.admin)
    assert client.put(f"/api/v1/users/{org.users.admin.id}", headers=h, json={"role": "OPERATOR"}).status_code == 400
    assert client.put(f"/api/v1/users/{org.users.admin.id}", headers=h, json={"is_active": False}).status_code == 400


def test_admin_user_management_flow(client, org, auth):
    h = auth(org.users.admin)
    r = client.post("/api/v1/users", headers=h, json={"name": "New Op", "email": "NEW@t.io", "password": "Abcdefgh1234",
                                                      "role": "OPERATOR", "facility_ids": [str(org.f2.id)]})
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert r.json()["email"] == "new@t.io" and r.json()["assignments"][0]["facility_id"] == str(org.f2.id)
    # weak password rejected
    assert client.post("/api/v1/users", headers=h, json={"name": "W", "email": "w@t.io", "password": "short",
                                                         "role": "OPERATOR"}).status_code == 422
    # region assignment only for supervisors
    assert client.put(f"/api/v1/users/{uid}/assignments", headers=h,
                      json={"region_ids": [str(org.regions.r1.id)]}).status_code == 400
    assert client.put(f"/api/v1/users/{uid}", headers=h, json={"is_active": False}).json()["is_active"] is False
    assert client.get("/api/v1/users/roles", headers=h).status_code == 200


def test_password_hash_never_returned(client, org, auth):
    r = client.get("/api/v1/users", headers=auth(org.users.admin))
    assert "password" not in r.text
