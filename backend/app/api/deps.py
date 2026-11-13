"""FastAPI dependencies: DB session, authentication, permission enforcement, data scope."""
import uuid
from typing import Callable, List

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import PERMISSIONS, permissions_for_role
from app.db.session import SessionLocal, engine, get_db  # noqa: F401  (re-exported for compatibility)
from app.models import User
from app.models.enums import Role
from app.security.auth import decode_access_token
from app.services.access import AccessScope, resolve_scope

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def user_from_token(db: Session, token: str) -> User:
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload.get("sub", ""))
    except (JWTError, ValueError, TypeError):
        raise _CREDENTIALS_EXC
    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_EXC
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")
    return user


def get_current_user(request: Request, db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    user = user_from_token(db, token)
    request.state.user = user
    return user


def get_scope(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AccessScope:
    return resolve_scope(db, user)


def require_permission(*permissions: str) -> Callable[..., AccessScope]:
    """Dependency factory: user must hold ALL listed permissions. Returns the AccessScope."""
    for p in permissions:
        if p not in PERMISSIONS:
            raise KeyError(f"Unknown permission '{p}'")

    def _dep(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AccessScope:
        granted = permissions_for_role(user.role)
        missing = [p for p in permissions if p not in granted]
        if missing:
            from app.services.audit import log_audit
            log_audit(db, user, "PERMISSION_DENIED", "Endpoint", None,
                      {"path": request.url.path, "method": request.method, "missing": missing},
                      category="SECURITY", outcome="DENIED", request=request)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted")
        return resolve_scope(db, user)

    return _dep


def require_any_permission(*permissions: str) -> Callable[..., AccessScope]:
    def _dep(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> AccessScope:
        granted = permissions_for_role(user.role)
        if not any(p in granted for p in permissions):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted")
        return resolve_scope(db, user)
    return _dep


class RequireRole:
    """Legacy (v1) dependency kept for backwards compatibility. New code must use
    `require_permission`."""

    def __init__(self, allowed_roles: List[Role]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operation not permitted")
        return current_user
