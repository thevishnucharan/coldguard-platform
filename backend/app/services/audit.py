import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import AuditLog, User

logger = logging.getLogger(__name__)

_NIL = uuid.UUID(int=0)
_SENSITIVE = {"password", "password_hash", "token", "secret", "device_key", "refresh_token"}


def _scrub(details: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (details or {}).items():
        if any(s in k.lower() for s in _SENSITIVE):
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = _scrub(v)
        elif isinstance(v, (uuid.UUID,)):
            out[k] = str(v)
        else:
            out[k] = v if isinstance(v, (str, int, float, bool, list, type(None))) else str(v)
    return out


def log_audit(
    db: Session,
    user: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[uuid.UUID],
    details: Dict[str, Any],
    *,
    category: str = "OPERATIONS",
    outcome: str = "SUCCESS",
    facility_id: Optional[uuid.UUID] = None,
    request=None,
    commit: bool = True,
) -> AuditLog:
    """Append an immutable audit record. `user=None` records a system action."""
    ip = None
    if request is not None:
        fwd = request.headers.get("X-Forwarded-For") if hasattr(request, "headers") else None
        ip = fwd.split(",")[0].strip() if fwd else (request.client.host if getattr(request, "client", None) else None)
    entry = AuditLog(
        user_id=user.id if user is not None else None,
        actor_name=user.name if user is not None else "system",
        actor_role=(user.role.value if hasattr(user.role, "value") else str(user.role)) if user is not None else "SYSTEM",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id or _NIL,
        details=_scrub(details),
        category=category,
        outcome=outcome,
        facility_id=facility_id,
        ip_address=ip,
    )
    db.add(entry)
    if commit:
        db.commit()
    return entry
