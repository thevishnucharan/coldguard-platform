"""Migrations are non-destructive: a DB at the ORIGINAL v1 schema with data upgrades to head
and keeps every row; a fresh DB upgrades cleanly."""
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, env=env, capture_output=True,
                          text=True, timeout=180)


def test_fresh_database_upgrades_to_head(tmp_path):
    url = f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}"
    r = _alembic(url, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    insp = sa.inspect(sa.create_engine(url))
    for t in ("facilities", "incident_events", "inventory_movements", "maintenance_tickets", "notifications",
              "route_plans"):
        assert insp.has_table(t)


def test_v1_data_survives_upgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}"
    assert _alembic(url, "upgrade", "8bda373ce97a").returncode == 0
    eng = sa.create_engine(url)
    now = datetime.now(timezone.utc)
    ids = {k: uuid.uuid4().hex for k in ("unit", "sensor", "user", "reading", "viol", "inc", "prod", "batch")}
    with eng.begin() as c:
        c.execute(sa.text("INSERT INTO users (id,name,email,password_hash,role,is_active,created_at,updated_at) "
                          "VALUES (:i,'Old Admin','old@x.io','h','ADMIN',1,:n,:n)"), {"i": ids["user"], "n": now})
        c.execute(sa.text("INSERT INTO storage_units (id,unit_code,name,location,unit_type,min_temperature,max_temperature,"
                          "status,created_at,updated_at) VALUES (:i,'OLD-1','Old fridge','x','ILR',2,8,'ACTIVE',:n,:n)"),
                  {"i": ids["unit"], "n": now})
        c.execute(sa.text("INSERT INTO sensors (id,sensor_code,storage_unit_id,sensor_type,status,created_at) "
                          "VALUES (:i,'OLD-S',:u,'t','ONLINE',:n)"), {"i": ids["sensor"], "u": ids["unit"], "n": now})
        c.execute(sa.text("INSERT INTO temperature_readings (id,storage_unit_id,sensor_id,temperature,timestamp,source,"
                          "quality_status,created_at) VALUES (:i,:u,:s,9.5,:n,'rest','valid',:n)"),
                  {"i": ids["reading"], "u": ids["unit"], "s": ids["sensor"], "n": now})
        c.execute(sa.text("INSERT INTO violations (id,storage_unit_id,start_time,peak_temperature,minimum_temperature,"
                          "allowed_minimum,allowed_maximum,duration_seconds,deviation,violation_type,severity,status,created_at) "
                          "VALUES (:i,:u,:n,9.5,9.5,2,8,60,1.5,'HIGH_EXCURSION','MAJOR','OPEN',:n)"),
                  {"i": ids["viol"], "u": ids["unit"], "n": now})
        c.execute(sa.text("INSERT INTO incidents (id,incident_number,violation_id,status,created_at) "
                          "VALUES (:i,'INC-OLD-1',:v,'OPEN',:n)"), {"i": ids["inc"], "v": ids["viol"], "n": now})
        c.execute(sa.text("INSERT INTO products (id,name,category,min_temperature,max_temperature,created_at) "
                          "VALUES (:i,'Old vaccine','x',2,8,:n)"), {"i": ids["prod"], "n": now})
        c.execute(sa.text("INSERT INTO batches (id,batch_number,product_id,storage_unit_id,start_time,expiry_date,status) "
                          "VALUES (:i,'OLD-B',:p,:u,:n,:n,'COMPLETED')"), {"i": ids["batch"], "p": ids["prod"], "u": ids["unit"], "n": now})
    r = _alembic(url, "upgrade", "head")
    assert r.returncode == 0, r.stderr
    with eng.connect() as c:
        assert c.execute(sa.text("SELECT COUNT(*) FROM temperature_readings")).scalar() == 1
        fac = c.execute(sa.text("SELECT facility_id FROM storage_units WHERE unit_code='OLD-1'")).scalar()
        assert fac is not None
        assert c.execute(sa.text("SELECT code FROM facilities")).scalar() == "LEGACY"
        inc = c.execute(sa.text("SELECT severity, facility_id, storage_unit_id, incident_type FROM incidents")).one()
        assert inc[0] == "HIGH" and inc[1] == fac and inc[2] is not None and inc[3] == "TEMPERATURE_EXCURSION"
        assert c.execute(sa.text("SELECT severity FROM violations")).scalar() == "HIGH"  # MAJOR mapped
        assert c.execute(sa.text("SELECT status, facility_id FROM batches")).one() == ("DEPLETED", fac)
    # the ORM can use the migrated DB
    from sqlalchemy.orm import Session
    from app.models import Incident
    with Session(eng) as s:
        assert s.query(Incident).one().incident_number == "INC-OLD-1"
