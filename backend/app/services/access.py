"""Data-scope resolution: which facilities may the current user see or act on?

Permissions answer *what* a user may do; AccessScope answers *where*. Every repository
query on facility-owned data goes through `scope.apply(query, Model.facility_id)` and every
single-resource lookup through `scope.ensure(facility_id)` so horizontal privilege
escalation (operator of facility A reading facility B) is blocked server-side.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable, Optional, Set

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.permissions import GLOBAL_SCOPE_ROLES, permissions_for_role
from app.models import Facility, User, UserRoleAssignment


@dataclass
class AccessScope:
    user: User
    is_global: bool
    facility_ids: Set[uuid.UUID] = field(default_factory=set)
    region_ids: Set[uuid.UUID] = field(default_factory=set)

    @property
    def permissions(self):
        return permissions_for_role(self.user.role)

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def can_access_facility(self, facility_id: Optional[uuid.UUID]) -> bool:
        if self.is_global:
            return True
        return facility_id is not None and facility_id in self.facility_ids

    def ensure(self, facility_id: Optional[uuid.UUID], *, not_found: str = "Resource not found") -> None:
        """Raise 404 (not 403) for out-of-scope resources so IDs cannot be enumerated."""
        if not self.can_access_facility(facility_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found)

    def ensure_requested(self, facility_id: Optional[uuid.UUID]) -> None:
        """For an explicitly requested facility filter: 403 if outside scope."""
        if facility_id is not None and not self.can_access_facility(facility_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Facility outside your assigned scope")

    def apply(self, query, facility_column):
        if self.is_global:
            return query
        if not self.facility_ids:
            return query.filter(False)
        return query.filter(facility_column.in_(self.facility_ids))

    def visible_facility_ids(self, db: Session) -> Iterable[uuid.UUID]:
        if self.is_global:
            return [f for (f,) in db.query(Facility.id).all()]
        return list(self.facility_ids)


def resolve_scope(db: Session, user: User) -> AccessScope:
    if user.role in GLOBAL_SCOPE_ROLES:
        return AccessScope(user=user, is_global=True)
    rows = db.query(UserRoleAssignment).filter(UserRoleAssignment.user_id == user.id).all()
    facility_ids = {r.facility_id for r in rows if r.facility_id}
    region_ids = {r.region_id for r in rows if r.region_id}
    if region_ids:
        facility_ids |= {fid for (fid,) in db.query(Facility.id).filter(Facility.region_id.in_(region_ids)).all()}
    return AccessScope(user=user, is_global=False, facility_ids=facility_ids, region_ids=region_ids)
