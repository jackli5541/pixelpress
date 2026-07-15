from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class Photo(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "photos"

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    taken_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    gps_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    device_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scene_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cleaning_recommendation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cleaning_issues: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cleaning_analysis_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cleaning_task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    cleaning_features: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cleaning_suggestion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cleaning_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    cleaning_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cleaning_decision_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cleaning_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    custom_caption: Mapped[str | None] = mapped_column(String(255), nullable=True)

    album = relationship("Album", back_populates="photos")
    chapter_links = relationship("ChapterPhoto", back_populates="photo", cascade="all, delete-orphan")
    page_links = relationship("PagePhoto", back_populates="photo", cascade="all, delete-orphan")
