import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.core.permissions import GLOBAL_SCOPE_ROLES, PERMISSIONS, ROLE_LABELS, ROLE_PERMISSIONS
from app.models import AuditLog, Facility, Region, User, UserRoleAssignment
from app.models.enums import Role
from app.schemas.common import Page, paginate
from app.schemas.user import AssignmentIn, UserCreate, UserDetail, UserResponse, UserUpdate
from app.security.auth import get_password_hash
from app.services.access import AccessScope
from app.services.audit import log_audit

router = APIRouter()


def _detail(db: Session, u: User) -> dict:
    data = UserResponse.model_validate(u).model_dump()
    data["assignments"] = [{"id": a.id, "facility_id": a.facility_id, "region_id": a.region_id,
                            "facility_name": a.facility.name if a.facility else None,
                            "region_name": a.region.name if a.region else None} for a in u.assignments]
    return data


def _set_assignments(db: Session, user: User, facility_ids, region_ids, actor: User):
    if user.role in GLOBAL_SCOPE_ROLES and (facility_ids or region_ids):
        raise HTTPException(400, "Administrators and auditors have platform-wide scope; no assignments needed")
    if region_ids and user.role != Role.SUPERVISOR:
        raise HTTPException(400, "Only supervisors can be assigned to whole regions")
    for fid in facility_ids:
        if not db.get(Facility, fid):
            raise HTTPException(400, f"Facility {fid} not found")
    for rid in region_ids:
        if not db.get(Region, rid):
            raise HTTPException(400, f"Region {rid} not found")
    db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).delete()
    for fid in set(facility_ids):
        db.add(UserRoleAssignment(user_id=user.id, role=user.role, facility_id=fid, assigned_by=actor.id))
    for rid in set(region_ids):
        db.add(UserRoleAssignment(user_id=user.id, role=user.role, region_id=rid, assigned_by=actor.id))


@router.get("/roles")
def role_matrix(_: AccessScope = Depends(require_permission("users.view"))):
    """The permission matrix (read-only)."""
    return {"roles": [{"code": r.value, "label": ROLE_LABELS[r], "global_scope": r in GLOBAL_SCOPE_ROLES,
                       "permissions": sorted(ROLE_PERMISSIONS[r])} for r in Role],
            "permissions": [{"code": k, "description": v} for k, v in PERMISSIONS.items()]}


@router.get("", response_model=Page[UserResponse])
def list_users(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=200), role: Optional[Role] = None,
               search: Optional[str] = Query(None, max_length=100), is_active: Optional[bool] = None,
               facility_id: Optional[uuid.UUID] = None, db: Session = Depends(get_db),
               _: AccessScope = Depends(require_permission("users.view"))) -> Any:
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    if is_active is not None:
        q = q.filter(User.is_active.is_(is_active))
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    if facility_id:
        fac = db.get(Facility, facility_id)
        q = q.join(UserRoleAssignment, UserRoleAssignment.user_id == User.id).filter(
            or_(UserRoleAssignment.facility_id == facility_id,
                UserRoleAssignment.region_id == (fac.region_id if fac else None))).distinct()
    items, total = paginate(q.order_by(User.name), page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/assignable")
def assignable_users(role: Role, facility_id: uuid.UUID, db: Session = Depends(get_db),
                     scope: AccessScope = Depends(require_permission("incidents.view"))):
    """Lightweight list for assignment pickers (operators/technicians of one facility)."""
    scope.ensure_requested(facility_id)
    if role not in (Role.OPERATOR, Role.TECHNICIAN):
        raise HTTPException(400, "Only operators and technicians are assignable")
    fac = db.get(Facility, facility_id)
    if not fac:
        raise HTTPException(404, "Facility not found")
    users = (db.query(User).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
             .filter(User.role == role, User.is_active.is_(True),
                     or_(UserRoleAssignment.facility_id == facility_id, UserRoleAssignment.region_id == fac.region_id))
             .distinct().order_by(User.name).all())
    return [{"id": u.id, "name": u.name, "title": u.title} for u in users]


@router.post("", response_model=UserDetail, status_code=201)
def create_user(body: UserCreate, request: Request, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("users.create", "users.assign_roles"))) -> Any:
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(409, "A user with this email already exists")
    u = User(name=body.name, email=email, role=body.role, title=body.title, phone=body.phone,
             password_hash=get_password_hash(body.password))
    db.add(u)
    db.flush()
    _set_assignments(db, u, body.facility_ids, body.region_ids, scope.user)
    log_audit(db, scope.user, "USER_CREATED", "User", u.id,
              {"email": email, "role": body.role.value, "facilities": [str(f) for f in body.facility_ids],
               "regions": [str(r) for r in body.region_ids]}, category="SECURITY", request=request, commit=False)
    db.commit()
    db.refresh(u)
    return _detail(db, u)


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db),
             _: AccessScope = Depends(require_permission("users.view"))) -> Any:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return _detail(db, u)


@router.put("/{user_id}", response_model=UserDetail)
def update_user(user_id: uuid.UUID, body: UserUpdate, request: Request, db: Session = Depends(get_db),
                scope: AccessScope = Depends(require_permission("users.update"))) -> Any:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    if "role" in data and data["role"] != u.role:
        if "users.assign_roles" not in scope.permissions:
            raise HTTPException(403, "Operation not permitted")
        if u.id == scope.user.id:
            raise HTTPException(400, "You cannot change your own role")
        db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == u.id).delete()
    if data.get("is_active") is False and u.id == scope.user.id:
        raise HTTPException(400, "You cannot deactivate your own account")
    if "email" in data and data["email"]:
        data["email"] = data["email"].lower()
        if db.query(User).filter(User.email == data["email"], User.id != u.id).first():
            raise HTTPException(409, "Email already in use")
    changes = {k: (v.value if hasattr(v, "value") else v) for k, v in data.items() if k != "password"}
    if data.get("password"):
        u.password_hash = get_password_hash(data.pop("password"))
        changes["password"] = "reset"
    else:
        data.pop("password", None)
    for k, v in data.items():
        setattr(u, k, v)
    if data.get("is_active") is True:
        u.locked_until, u.failed_login_count = None, 0
    log_audit(db, scope.user, "USER_UPDATED", "User", u.id, changes, category="SECURITY", request=request, commit=False)
    db.commit()
    db.refresh(u)
    return _detail(db, u)


@router.put("/{user_id}/assignments", response_model=UserDetail)
def set_assignments(user_id: uuid.UUID, body: AssignmentIn, request: Request, db: Session = Depends(get_db),
                    scope: AccessScope = Depends(require_permission("users.assign_roles"))) -> Any:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    _set_assignments(db, u, body.facility_ids, body.region_ids, scope.user)
    log_audit(db, scope.user, "USER_SCOPE_CHANGED", "User", u.id,
              {"facilities": [str(f) for f in body.facility_ids], "regions": [str(r) for r in body.region_ids]},
              category="SECURITY", request=request, commit=False)
    db.commit()
    db.refresh(u)
    return _detail(db, u)


@router.get("/{user_id}/activity")
def user_activity(user_id: uuid.UUID, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                  _: AccessScope = Depends(require_permission("users.view", "audit.view"))) -> List[dict]:
    rows = (db.query(AuditLog).filter(AuditLog.user_id == user_id).order_by(AuditLog.timestamp.desc()).limit(limit).all())
    return [{"id": a.id, "action": a.action, "entity_type": a.entity_type, "category": a.category,
             "outcome": a.outcome, "timestamp": a.timestamp, "ip_address": a.ip_address} for a in rows]
