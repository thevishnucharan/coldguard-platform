"""In-app notifications + recipient resolution by facility responsibility."""
import uuid
from typing import Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.metrics import NOTIFICATIONS
from app.models import Facility, Notification, User, UserRoleAssignment
from app.models.enums import NotificationLevel, Role
from app.services import realtime


def responsible_users(db: Session, facility_id: Optional[uuid.UUID], roles: Sequence[Role]) -> List[User]:
    """Active users of the given roles responsible for a facility: direct facility
    assignment, or region assignment covering it."""
    if facility_id is None:
        return []
    facility = db.get(Facility, facility_id)
    if not facility:
        return []
    q = (db.query(User).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
         .filter(User.is_active.is_(True), User.role.in_(list(roles)))
         .filter((UserRoleAssignment.facility_id == facility_id) | (UserRoleAssignment.region_id == facility.region_id)))
    return q.distinct().all()


def notify(db: Session, users: Iterable[User], title: str, message: str, *,
           level: NotificationLevel = NotificationLevel.INFO, category: str = "SYSTEM",
           link: Optional[str] = None, entity_type: Optional[str] = None,
           entity_id: Optional[uuid.UUID] = None, facility_id: Optional[uuid.UUID] = None,
           commit: bool = True) -> List[Notification]:
    created = []
    seen = set()
    for u in users:
        if u.id in seen:
            continue
        seen.add(u.id)
        n = Notification(user_id=u.id, title=title, message=message, level=level, category=category,
                         link=link, entity_type=entity_type, entity_id=entity_id)
        db.add(n)
        created.append(n)
        NOTIFICATIONS.labels(level=level.value).inc()
    if commit:
        db.commit()
    else:
        db.flush()
    if created:
        realtime.publish("notification", {"title": title, "message": message, "level": level.value,
                                          "category": category, "link": link},
                         facility_id=facility_id, user_ids=[n.user_id for n in created])
    return created


def notify_facility(db: Session, facility_id, roles: Sequence[Role], title: str, message: str, **kw):
    return notify(db, responsible_users(db, facility_id, roles), title, message, facility_id=facility_id, **kw)
