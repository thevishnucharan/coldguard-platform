"""Test fixtures.

A file-backed SQLite DB (not :memory:) is used so code paths that open their own sessions
(SessionLocal in ingestion/worker/WebSocket) see the same data as the request session.
Environment is set BEFORE the app is imported.
"""
import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

_tmp = tempfile.mkdtemp(prefix="coldguard-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{os.path.join(_tmp, 'test.db').replace(os.sep, '/')}",
    "ENVIRONMENT": "test", "RUN_EMBEDDED_WORKER": "false", "SIMULATION_ENABLED": "false", "MQTT_ENABLED": "false",
    "REDIS_URL": "", "DEMO_MODE": "true", "INGEST_API_KEY": "test-ingest-key-0123456789", "LOG_LEVEL": "WARNING",
    "SECRET_KEY": "test-secret-key-that-is-long-enough-0123456789",
})

import pytest  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.models import (Facility, MonitoringPolicy, Product, Region, Sensor, StorageUnit, User,  # noqa: E402
                        UserRoleAssignment)
from app.models.enums import Role, SensorStatus  # noqa: E402
from app.security.auth import create_access_token, get_password_hash  # noqa: E402

PASSWORD = "Correct-Horse-42"
_HASH = get_password_hash(PASSWORD)


@pytest.fixture(autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core.middleware import limiter
    limiter.reset()
    from app.ml.anomaly_service import MLAnomalyService
    MLAnomalyService._loaded = False
    yield


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


def headers_for(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def auth():
    return headers_for


def _user(db, email, role, **kw):
    u = User(name=email.split("@")[0], email=email, role=role, password_hash=_HASH, **kw)
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def org(db):
    """Two regions; R1 has F1 & F2, R2 has F3. One 2–8 °C unit + sensor per facility,
    plus a freezer in F1. Users of every role with realistic scopes."""
    now = datetime.now(timezone.utc)
    pol = MonitoringPolicy(name="2-8", min_temperature=2, max_temperature=8, warning_margin=0.5,
                           critical_after_minutes=30, critical_deviation=3, expected_interval_seconds=60,
                           missing_telemetry_minutes=5, offline_minutes=15)
    frz = MonitoringPolicy(name="freezer", min_temperature=-25, max_temperature=-15, warning_margin=1,
                           critical_after_minutes=30, critical_deviation=4, expected_interval_seconds=60,
                           missing_telemetry_minutes=5, offline_minutes=15)
    db.add_all([pol, frz])
    r1, r2 = Region(code="R1", name="Region One"), Region(code="R2", name="Region Two")
    db.add_all([r1, r2])
    db.flush()
    f1 = Facility(code="F1", name="Facility One", region_id=r1.id)
    f2 = Facility(code="F2", name="Facility Two", region_id=r1.id)
    f3 = Facility(code="F3", name="Facility Three", region_id=r2.id)
    db.add_all([f1, f2, f3])
    db.flush()
    units, sensors = {}, {}
    for key, fac, p in (("u1", f1, pol), ("u2", f2, pol), ("u3", f3, pol), ("fz1", f1, frz)):
        u = StorageUnit(unit_code=key.upper(), name=key, location="room", unit_type="ILR", facility_id=fac.id,
                        policy_id=p.id, min_temperature=p.min_temperature, max_temperature=p.max_temperature)
        db.add(u)
        db.flush()
        s = Sensor(sensor_code=f"S-{key.upper()}", storage_unit_id=u.id, sensor_type="temp", status=SensorStatus.ONLINE,
                   battery_level=90, calibration_due_at=now + timedelta(days=200), created_at=now)
        db.add(s)
        db.flush()
        units[key], sensors[key] = u, s
    users = {
        "admin": _user(db, "admin@t.io", Role.ADMIN),
        "op1": _user(db, "op1@t.io", Role.OPERATOR),
        "op1b": _user(db, "op1b@t.io", Role.OPERATOR),
        "op3": _user(db, "op3@t.io", Role.OPERATOR),
        "sup1": _user(db, "sup1@t.io", Role.SUPERVISOR),
        "sup2": _user(db, "sup2@t.io", Role.SUPERVISOR),
        "tech1": _user(db, "tech1@t.io", Role.TECHNICIAN),
        "tech3": _user(db, "tech3@t.io", Role.TECHNICIAN),
        "auditor": _user(db, "auditor@t.io", Role.AUDITOR),
    }
    a = lambda u, **kw: db.add(UserRoleAssignment(user_id=u.id, role=u.role, **kw))  # noqa: E731
    a(users["op1"], facility_id=f1.id)
    a(users["op1b"], facility_id=f1.id)
    a(users["op3"], facility_id=f3.id)
    a(users["sup1"], region_id=r1.id)
    a(users["sup2"], region_id=r2.id)
    a(users["tech1"], facility_id=f1.id)
    a(users["tech1"], facility_id=f2.id)
    a(users["tech3"], facility_id=f3.id)
    product = Product(name="Penta", category="Routine", min_temperature=2, max_temperature=8)
    frozen = Product(name="OPV", category="Routine", min_temperature=-25, max_temperature=8)
    db.add_all([product, frozen])
    db.commit()
    return SimpleNamespace(policy=pol, freezer=frz, regions=SimpleNamespace(r1=r1, r2=r2),
                           f1=f1, f2=f2, f3=f3, units=SimpleNamespace(**units), sensors=SimpleNamespace(**sensors),
                           users=SimpleNamespace(**users), product=product, frozen=frozen)


def reading(sensor_code, temp, minutes_ago=0.0, **kw):
    ts = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"sensor_code": sensor_code, "temperature": temp, "timestamp": ts.isoformat(),
            "message_id": kw.pop("message_id", uuid.uuid4().hex), **kw}


def feed(db, sensor_code, temps, start_minutes_ago, step_minutes=1.0):
    """Push a series through the real pipeline, oldest first."""
    from app.services import telemetry
    out = []
    for i, t in enumerate(temps):
        out.append(telemetry.ingest(db, reading(sensor_code, t, start_minutes_ago - i * step_minutes), channel="test"))
    return out
