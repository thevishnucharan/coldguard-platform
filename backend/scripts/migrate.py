#!/usr/bin/env python3
"""Apply database migrations safely.

Databases created by ColdGuard v1 via `create_all()` have tables but no `alembic_version`
row; they are stamped at the original revision (8bda373ce97a) first so the defensive,
non-destructive 0002 migration upgrades them in place without dropping data.

    python scripts/migrate.py                 # uses DATABASE_URL / .env
"""
import os
import subprocess
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import sqlalchemy as sa  # noqa: E402

from app.core.config import settings  # noqa: E402


def main() -> int:
    url = os.environ.get("DATABASE_URL", settings.DATABASE_URL)
    eng = sa.create_engine(url)
    insp = sa.inspect(eng)
    if insp.has_table("users") and not insp.has_table("alembic_version"):
        with eng.begin() as c:
            c.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            c.execute(sa.text("INSERT INTO alembic_version VALUES ('8bda373ce97a')"))
        print("[migrate] legacy v1 schema detected -> stamped 8bda373ce97a")
    eng.dispose()
    return subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND,
                           env={**os.environ, "DATABASE_URL": url})


if __name__ == "__main__":
    sys.exit(main())
