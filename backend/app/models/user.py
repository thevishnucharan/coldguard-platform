import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, TimestampMixin, UUIDMixin, enum_type, utcnow
from app.models.enums import Role


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(enum_type(Role), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    assigned_incidents: Mapped[List["Incident"]] = relationship(
        back_populates="assignee", foreign_keys="Incident.assigned_to")
    audit_logs: Mapped[List["AuditLog"]] = relationship(back_populates="user")
    assignments: Mapped[List["UserRoleAssignment"]] = relationship(
        back_populates="user", foreign_keys="UserRoleAssignment.user_id", cascade="all, delete-orphan")


class RefreshToken(Base, UUIDMixin):
    """Opaque refresh tokens, stored hashed. Rotated on every use; reuse of a revoked
    token revokes the whole family (token theft detection)."""
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
