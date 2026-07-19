from __future__ import annotations

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ChapterPhoto(Base):
    __tablename__ = "chapter_photos"
    __table_args__ = (
        UniqueConstraint("chapter_id", "photo_id", name="uq_chapter_photos_chapter_photo"),
        UniqueConstraint("chapter_id", "order_index", name="uq_chapter_photos_chapter_order"),
        Index("ix_chapter_photos_segment_id", "segment_id"),
    )

    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True)
    segment_id: Mapped[str | None] = mapped_column(
        ForeignKey("chapter_segments.id", ondelete="SET NULL"),
        nullable=True,
    )
    order_index: Mapped[int] = mapped_column(nullable=False)

    chapter = relationship("Chapter", back_populates="photo_links")
    segment = relationship("ChapterSegment", back_populates="photo_links")
    photo = relationship("Photo", back_populates="chapter_links")
