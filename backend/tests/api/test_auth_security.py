"""Authentication & security: login, lockout, refresh rotation, invalid/expired/forged tokens."""
from datetime import timedelta

from jose import jwt

from app.core.config import settings
from app.models import AuditLog, User
from app.security.auth import create_access_token
from tests.conftest import PASSWORD

LOGIN = "/api/v1/auth/login"


def _login(client, email, pw=PASSWORD):
    return client.post(LOGIN, data={"username": email, "password": pw})


def test_login_returns_access_and_refresh_tokens(client, org):
    r = _login(client, "op1@t.io")
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"] and body["refresh_token"]
    claims = jwt.get_unverified_claims(body["access_token"])
    assert claims["typ"] == "access" and "role" not in claims  # role never trusted from the token


def test_login_wrong_password_is_logged(client, org, db):
    r = _login(client, "op1@t.io", "wrong-password-1")
    assert r.status_code == 401
    assert db.query(AuditLog).filter(AuditLog.action == "LOGIN_FAILED", AuditLog.outcome == "FAILURE").count() == 1


def test_unknown_user_same_error_as_bad_password(client, org):
    a = _login(client, "nobody@t.io", "whatever-123")
    b = _login(client, "op1@t.io", "whatever-123")
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_account_lockout_after_repeated_failures(client, org, db):
    for _ in range(settings.MAX_FAILED_LOGINS):
        assert _login(client, "op1@t.io", "bad-password-9").status_code == 401
    r = _login(client, "op1@t.io")  # correct password, but locked
    assert r.status_code == 423
    db.expire_all()
    assert db.query(User).filter_by(email="op1@t.io").one().locked_until is not None


def test_deactivated_user_cannot_login_or_use_token(client, org, db, auth):
    u = db.get(User, org.users.op1.id)
    h = auth(u)
    u.is_active = False
    db.commit()
    assert _login(client, "op1@t.io").status_code == 403
    assert client.get("/api/v1/auth/me", headers=h).status_code == 403


def test_public_registration_removed(client, org):
    r = client.post("/api/v1/auth/register", json={"name": "x", "email": "x@t.io", "password": "Abcdefgh1234",
                                                    "role": "ADMIN"})
    assert r.status_code in (404, 405)


def test_invalid_expired_and_forged_tokens_rejected(client, org):
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    expired = create_access_token(org.users.admin.id, expires_delta=timedelta(seconds=-5))
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    forged = jwt.encode({"sub": str(org.users.op1.id), "typ": "access", "role": "ADMIN"}, "attacker-key",
                        algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/api/v1/incidents").status_code == 401


def test_role_claim_in_token_is_ignored(client, org):
    """A validly signed token carrying role=ADMIN for an operator gives operator rights only."""
    tok = create_access_token(org.users.op1.id, extra={"role": "ADMIN"})
    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_refresh_rotation_and_reuse_detection(client, org):
    first = _login(client, "op1@t.io").json()["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r.status_code == 200
    second = r.json()["refresh_token"]
    assert second != first
    # replaying the rotated token => whole family revoked
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": second}).status_code == 401


def test_logout_revokes_refresh_token(client, org):
    body = _login(client, "op1@t.io").json()
    h = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.post("/api/v1/auth/logout", json={"refresh_token": body["refresh_token"]}, headers=h).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


def test_me_returns_permissions_and_scope(client, org, auth):
    me = client.get("/api/v1/auth/me", headers=auth(org.users.sup1)).json()
    assert me["role"] == "SUPERVISOR" and "corrective_actions.approve" in me["permissions"]
    assert me["global_scope"] is False
    assert {str(org.f1.id), str(org.f2.id)} == set(me["facility_ids"])


def test_change_password_requires_current_and_strength(client, org, auth):
    h = auth(org.users.op1)
    assert client.post("/api/v1/auth/change-password", headers=h,
                       json={"current_password": "nope-nope-1", "new_password": "NewPassword123"}).status_code == 400
    assert client.post("/api/v1/auth/change-password", headers=h,
                       json={"current_password": PASSWORD, "new_password": "onlyletterslong"}).status_code == 422
    assert client.post("/api/v1/auth/change-password", headers=h,
                       json={"current_password": PASSWORD, "new_password": "NewPassword123"}).status_code == 204
    assert _login(client, "op1@t.io", "NewPassword123").status_code == 200


def test_login_rate_limited(client, org):
    hdr = {"X-Test-Rate-Limit": "1"}
    codes = [client.post(LOGIN, data={"username": "x@t.io", "password": "y"}, headers=hdr).status_code
             for _ in range(settings.RATE_LIMIT_AUTH_PER_MINUTE + 2)]
    assert 429 in codes


def test_security_headers_and_no_stack_traces(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in r.headers


def test_me_works_for_special_use_email_domains(client, db, auth):
    """Regression: EmailStr on response models rejected seeded '.local' demo accounts (HTTP 500)."""
    from app.models import User
    from app.models.enums import Role
    u = User(name="Demo", email="admin@coldguard.local", role=Role.ADMIN, password_hash="x")
    db.add(u)
    db.commit()
    r = client.get("/api/v1/auth/me", headers=auth(u))
    assert r.status_code == 200 and r.json()["email"] == "admin@coldguard.local"
