import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_permission
from app.models import Notification
from app.services.access import AccessScope

router = APIRouter()


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
                       scope: AccessScope = Depends(require_permission("notifications.view"))):
    q = db.query(Notification).filter(Notification.user_id == scope.user.id)
    if unread_only:
        q = q.filter(Notification.read_at.is_(None))
    unread = db.query(Notification).filter(Notification.user_id == scope.user.id, Notification.read_at.is_(None)).count()
    return {"unread": unread, "items": [
        {"id": n.id, "level": n.level.value, "category": n.category, "title": n.title, "message": n.message,
         "link": n.link, "created_at": n.created_at, "read_at": n.read_at}
        for n in q.order_by(Notification.created_at.desc()).limit(limit)]}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: uuid.UUID, db: Session = Depends(get_db),
              scope: AccessScope = Depends(require_permission("notifications.view"))):
    n = db.get(Notification, notification_id)
    if not n or n.user_id != scope.user.id:  # users can only touch their own notifications
        raise HTTPException(404, "Notification not found")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all(db: Session = Depends(get_db), scope: AccessScope = Depends(require_permission("notifications.view"))):
    db.query(Notification).filter(Notification.user_id == scope.user.id, Notification.read_at.is_(None)) \
        .update({"read_at": datetime.now(timezone.utc)})
    db.commit()
