from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ChapterSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chapter_segments"
    __table_args__ = (
        UniqueConstraint("chapter_id", "order_index", name="uq_chapter_segments_chapter_order"),
    )

    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="活动阶段", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(nullable=False)
    segment_type: Mapped[str] = mapped_column(String(64), default="scene", nullable=False)
    time_range: Mapped[str | None] = mapped_column(String(128), nullable=True)
    clustering_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    clustering_needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    clustering_explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    chapter = relationship("Chapter", back_populates="segments")
    photo_links = relationship("ChapterPhoto", back_populates="segment")
