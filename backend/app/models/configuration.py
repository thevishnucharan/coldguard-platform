from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, JSON, DateTime
from datetime import datetime, timezone
from app.db.base import UTCDateTime, Base
from typing import Any, Optional

class SystemConfiguration(Base):
    __tablename__ = "system_configurations"

    key: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

