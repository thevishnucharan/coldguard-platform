import enum
import uuid
from datetime import datetime, timezone
from typing import Type

from sqlalchemy import DateTime, Enum
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_type(enum_cls: Type[enum.Enum]) -> Enum:
    """Portable enum column: stored as VARCHAR (no native DB enum) so new states can be
    added without `ALTER TYPE` migrations on PostgreSQL. Values are still validated."""
    return Enum(enum_cls, native_enum=False, length=40, validate_strings=True,
                values_callable=lambda e: [m.value for m in e])


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend. SQLite has no tz support and returns
    naive values, which the API would serialise without an offset (browsers then parse them
    as LOCAL time). Values are normalised to UTC on write and tagged UTC on read."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=True
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; normalise everything to aware UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
