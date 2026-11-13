import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, TimestampMixin, UUIDMixin, enum_type, utcnow
from app.models.enums import Role


class Region(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "regions"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    facilities: Mapped[List["Facility"]] = relationship(back_populates="region")


class Facility(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "facilities"

    code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    facility_type: Mapped[str] = mapped_column(String(60), nullable=False, default="Health Facility")
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id"), nullable=False, index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    region: Mapped["Region"] = relationship(back_populates="facilities")
    storage_units: Mapped[List["StorageUnit"]] = relationship(back_populates="facility")


class UserRoleAssignment(Base, UUIDMixin):
    """Data-scope assignment. A user's *permissions* come from `users.role`;
    *which facilities* they may act on comes from these rows:
      - facility_id set  -> that facility
      - region_id set    -> every facility in that region (supervisors)
    ADMIN and AUDITOR have global scope and need no rows."""
    __tablename__ = "user_role_assignments"
    __table_args__ = (UniqueConstraint("user_id", "facility_id", "region_id", name="uq_user_scope"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[Role] = mapped_column(enum_type(Role), nullable=False)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    region_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("regions.id"), nullable=True, index=True)
    assigned_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="assignments", foreign_keys=[user_id])
    facility: Mapped[Optional["Facility"]] = relationship()
    region: Mapped[Optional["Region"]] = relationship()


class RoleDefinition(Base):
    __tablename__ = "roles"
    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    global_scope: Mapped[bool] = mapped_column(Boolean, default=False)


class Permission(Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_code: Mapped[str] = mapped_column(ForeignKey("roles.code", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code", ondelete="CASCADE"), primary_key=True)
