"""Persist the code-defined permission matrix to roles/permissions/role_permissions so it is
queryable (admin UI, auditors). Idempotent; run at startup."""
from sqlalchemy.orm import Session

from app.core.permissions import GLOBAL_SCOPE_ROLES, PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS
from app.models import Permission, RoleDefinition, RolePermission


def sync_rbac(db: Session) -> None:
    existing_perms = {p.code: p for p in db.query(Permission).all()}
    for code, desc in PERMISSIONS.items():
        if code in existing_perms:
            existing_perms[code].description = desc
        else:
            db.add(Permission(code=code, description=desc))
    for role, label in ROLE_LABELS.items():
        r = db.get(RoleDefinition, role.value)
        if r:
            r.label, r.global_scope = label, role in GLOBAL_SCOPE_ROLES
        else:
            db.add(RoleDefinition(code=role.value, label=label, global_scope=role in GLOBAL_SCOPE_ROLES))
    db.flush()
    current = {(rp.role_code, rp.permission_code) for rp in db.query(RolePermission).all()}
    wanted = {(role.value, p) for role, perms in ROLE_PERMISSIONS.items() for p in perms}
    for rc, pc in wanted - current:
        db.add(RolePermission(role_code=rc, permission_code=pc))
    for rc, pc in current - wanted:
        db.query(RolePermission).filter_by(role_code=rc, permission_code=pc).delete()
    db.commit()
