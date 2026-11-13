"""Authentication: password login (OAuth2 form), refresh-token rotation, logout, profile.

Public self-registration from v1 was removed: it allowed creating privileged accounts.
Accounts are created by administrators (`POST /users`).
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_scope
from app.core.config import settings
from app.core.permissions import ROLE_LABELS
from app.db.base import as_utc
from app.models import RefreshToken, User
from app.schemas.auth import ChangePasswordRequest, RefreshRequest, Token
from app.schemas.user import MeResponse
from app.security.auth import (create_access_token, dummy_verify, get_password_hash, hash_token, new_refresh_token,
                               verify_password)
from app.services.access import AccessScope
from app.services.audit import log_audit

router = APIRouter()
_BAD_LOGIN = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password",
                           headers={"WWW-Authenticate": "Bearer"})


def _issue(db: Session, user: User, request: Request, family: uuid.UUID | None = None) -> dict:
    plain, digest = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=digest, family_id=family or uuid.uuid4(),
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
                        user_agent=(request.headers.get("user-agent") or "")[:255]))
    db.commit()
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "refresh_token": plain,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60}


@router.post("/login", response_model=Token)
def login(request: Request, db: Session = Depends(get_db), form: OAuth2PasswordRequestForm = Depends()) -> Any:
    email = form.username.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    now = datetime.now(timezone.utc)
    if user is None:
        dummy_verify()  # equalise timing so valid e-mails cannot be enumerated
        log_audit(db, None, "LOGIN_FAILED", "User", None, {"email": email[:120], "reason": "unknown_user"},
                  category="SECURITY", outcome="FAILURE", request=request)
        raise _BAD_LOGIN
    if user.locked_until and as_utc(user.locked_until) > now:
        log_audit(db, user, "LOGIN_BLOCKED", "User", user.id, {"reason": "locked"}, category="SECURITY",
                  outcome="DENIED", request=request)
        raise HTTPException(status_code=423, detail="Account temporarily locked after repeated failed logins")
    if not verify_password(form.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        details = {"reason": "bad_password", "failed_count": user.failed_login_count}
        if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=settings.LOCKOUT_MINUTES)
            user.failed_login_count = 0
            details["locked_until"] = user.locked_until.isoformat()
        log_audit(db, user, "LOGIN_FAILED", "User", user.id, details, category="SECURITY", outcome="FAILURE",
                  request=request)
        raise _BAD_LOGIN
    if not user.is_active:
        log_audit(db, user, "LOGIN_BLOCKED", "User", user.id, {"reason": "inactive"}, category="SECURITY",
                  outcome="DENIED", request=request)
        raise HTTPException(status_code=403, detail="Account is deactivated")
    user.failed_login_count, user.locked_until, user.last_login_at = 0, None, now
    log_audit(db, user, "LOGIN", "User", user.id, {"method": "password"}, category="SECURITY", request=request,
              commit=False)
    return _issue(db, user, request)


@router.post("/refresh", response_model=Token)
def refresh(body: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> Any:
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(body.refresh_token)).first()
    now = datetime.now(timezone.utc)
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if row.revoked_at is not None:
        # Reuse of a rotated token => likely theft. Revoke the entire family.
        db.query(RefreshToken).filter(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None)) \
            .update({"revoked_at": now})
        log_audit(db, db.get(User, row.user_id), "REFRESH_TOKEN_REUSE", "User", row.user_id, {},
                  category="SECURITY", outcome="DENIED", request=request)
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; please sign in again")
    if as_utc(row.expires_at) < now:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Account unavailable")
    row.revoked_at = now
    return _issue(db, user, request, family=row.family_id)


@router.post("/logout", status_code=204)
def logout(body: RefreshRequest, request: Request, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(body.refresh_token),
                                        RefreshToken.user_id == user.id).first()
    if row:
        db.query(RefreshToken).filter(RefreshToken.family_id == row.family_id).update(
            {"revoked_at": datetime.now(timezone.utc)})
    log_audit(db, user, "LOGOUT", "User", user.id, {}, category="SECURITY", request=request)


@router.get("/me", response_model=MeResponse)
def me(scope: AccessScope = Depends(get_scope)) -> Any:
    u = scope.user
    return {**{c: getattr(u, c) for c in ("id", "name", "email", "role", "is_active", "title", "phone",
                                          "last_login_at", "created_at", "updated_at", "locked_until")},
            "permissions": sorted(scope.permissions), "role_label": ROLE_LABELS[u.role],
            "global_scope": scope.is_global, "facility_ids": sorted(scope.facility_ids, key=str),
            "region_ids": sorted(scope.region_ids, key=str)}


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordRequest, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.password_hash):
        log_audit(db, user, "PASSWORD_CHANGE_FAILED", "User", user.id, {}, category="SECURITY", outcome="FAILURE",
                  request=request)
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    from app.schemas.user import _strong
    try:
        _strong(body.new_password)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    user.password_hash = get_password_hash(body.new_password)
    db.query(RefreshToken).filter(RefreshToken.user_id == user.id).update({"revoked_at": datetime.now(timezone.utc)})
    log_audit(db, user, "PASSWORD_CHANGED", "User", user.id, {}, category="SECURITY", request=request)
