import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import UTCDateTime, Base, UUIDMixin, enum_type, utcnow
from app.models.enums import NotificationLevel


class AuditLog(Base, UUIDMixin):
    """Append-only audit trail (update/delete blocked in app/db/immutability.py)."""
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    actor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    category: Mapped[str] = mapped_column(String(30), default="OPERATIONS", nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    facility_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("facilities.id"), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="SUCCESS", nullable=False)

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_logs")


class Notification(Base, UUIDMixin):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_read", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level: Mapped[NotificationLevel] = mapped_column(enum_type(NotificationLevel), default=NotificationLevel.INFO)
    category: Mapped[str] = mapped_column(String(40), default="SYSTEM")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
