from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class PhotoThemeDecisionEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "photo_theme_decision_events"

    profile_id: Mapped[str] = mapped_column(ForeignKey("album_theme_profiles.id", ondelete="CASCADE"), nullable=False)
    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

