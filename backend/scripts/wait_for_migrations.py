#!/usr/bin/env python3
"""Block until the database schema is at the Alembic head revision (used as a Kubernetes
initContainer so API/worker pods never start against an un-migrated database; the
migration itself runs once, in the coldguard-migrate Job)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sqlalchemy as sa  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
head = ScriptDirectory.from_config(Config(os.path.join(BACKEND, "alembic.ini"))).get_current_head()
url = os.environ["DATABASE_URL"]
deadline = time.time() + int(os.environ.get("MIGRATION_WAIT_SECONDS", "600"))
while time.time() < deadline:
    try:
        with sa.create_engine(url).connect() as c:
            if c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == head:
                print(f"[wait] schema at head {head}")
                sys.exit(0)
    except Exception as exc:  # DB not up / table missing yet
        print(f"[wait] not ready: {str(exc)[:120]}")
    time.sleep(5)
sys.exit("[wait] timed out waiting for migrations")
