from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Chapter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chapters"

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="Untitled", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(default=0, nullable=False)
    clustering_source: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    clustering_algorithm_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    clustering_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    clustering_needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    clustering_explanation: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    album = relationship("Album", back_populates="chapters")
    photo_links = relationship("ChapterPhoto", back_populates="chapter", cascade="all, delete-orphan")
    segments = relationship(
        "ChapterSegment",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterSegment.order_index",
    )
    pages = relationship("Page", back_populates="chapter")
