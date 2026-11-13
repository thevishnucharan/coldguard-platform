import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models import AuditLog
from app.schemas.common import paginate
from app.services.access import AccessScope

router = APIRouter()


@router.get("")
def list_audit_logs(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                    category: Optional[str] = Query(None, max_length=30), action: Optional[str] = Query(None, max_length=100),
                    user_id: Optional[uuid.UUID] = None, entity_type: Optional[str] = None,
                    entity_id: Optional[uuid.UUID] = None, outcome: Optional[str] = None,
                    facility_id: Optional[uuid.UUID] = None, start: Optional[datetime] = None,
                    end: Optional[datetime] = None, search: Optional[str] = Query(None, max_length=100),
                    db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("audit.view"))):
    scope.ensure_requested(facility_id)
    q = scope.apply(db.query(AuditLog), AuditLog.facility_id)  # supervisors: own region only
    for col, val in ((AuditLog.category, category), (AuditLog.user_id, user_id), (AuditLog.entity_type, entity_type),
                     (AuditLog.entity_id, entity_id), (AuditLog.outcome, outcome), (AuditLog.facility_id, facility_id)):
        if val:
            q = q.filter(col == val)
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    if start:
        q = q.filter(AuditLog.timestamp >= start)
    if end:
        q = q.filter(AuditLog.timestamp <= end)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(AuditLog.action.ilike(like), AuditLog.actor_name.ilike(like), AuditLog.entity_type.ilike(like)))
    items, total = paginate(q.order_by(AuditLog.timestamp.desc()), page, page_size)
    return {"items": [{"id": a.id, "timestamp": a.timestamp, "user_id": a.user_id, "actor_name": a.actor_name,
                       "actor_role": a.actor_role, "action": a.action, "category": a.category, "outcome": a.outcome,
                       "entity_type": a.entity_type, "entity_id": a.entity_id, "facility_id": a.facility_id,
                       "ip_address": a.ip_address, "details": a.details} for a in items],
            "total": total, "page": page, "page_size": page_size}
