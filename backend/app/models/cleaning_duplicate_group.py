from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class CleaningDuplicateGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cleaning_duplicate_groups"

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    analysis_version: Mapped[str] = mapped_column(String(64), nullable=False)
    group_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    preferred_photo_id: Mapped[str | None] = mapped_column(ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    thresholds_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    explanation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    members = relationship("CleaningDuplicateMember", back_populates="group", cascade="all, delete-orphan")
