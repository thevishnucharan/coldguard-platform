#!/usr/bin/env python3
"""ColdGuard seed / bootstrap (idempotent).

    python scripts/seed.py            # demo dataset if the DB is empty and DEMO_MODE=true
    python scripts/seed.py --reset    # DEMO ONLY: wipe everything and re-seed
    python scripts/seed.py --bootstrap-admin admin@example.org   # production first admin
                                         (password read from BOOTSTRAP_ADMIN_PASSWORD)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import User  # noqa: E402
from app.models.enums import Role  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--bootstrap-admin")
    ap.add_argument("--no-scenarios", action="store_true")
    args = ap.parse_args()
    db = SessionLocal()
    try:
        from app.services.rbac import sync_rbac
        sync_rbac(db)
        if args.bootstrap_admin:
            pw = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
            if not pw or len(pw) < 12:
                sys.exit("Set BOOTSTRAP_ADMIN_PASSWORD (>=12 chars)")
            if db.query(User).filter(User.email == args.bootstrap_admin.lower()).first():
                print("Admin already exists")
                return
            from app.security.auth import get_password_hash
            db.add(User(name="Administrator", email=args.bootstrap_admin.lower(), role=Role.ADMIN,
                        password_hash=get_password_hash(pw)))
            db.commit()
            print("Bootstrap admin created")
            return
        if not settings.DEMO_MODE:
            print("DEMO_MODE=false: skipping demo seed")
            return
        from app.services import demo_seed
        if args.reset:
            demo_seed.wipe(db)
        if db.query(User).count() > 0:
            print(f"Database already has {db.query(User).count()} users — demo seed skipped (use --reset)")
            return
        print("Seeding demo dataset (simulated data)...")
        print(demo_seed.seed(db, with_scenarios=not args.no_scenarios))
    finally:
        db.close()


if __name__ == "__main__":
    main()
