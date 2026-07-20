from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AlbumThemeProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "album_theme_profiles"
    __table_args__ = (
        Index("ix_album_theme_profiles_album_status", "album_id", "status"),
    )

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    analysis_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    selection_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    analysis_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    constraints_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    candidates_json: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    chapter_strategy: Mapped[str] = mapped_column(String(32), default="balanced", nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    custom_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    album = relationship("Album", back_populates="theme_profiles")
    assessments = relationship(
        "PhotoThemeAssessment",
        back_populates="profile",
        cascade="all, delete-orphan",
    )
