from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Page(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("album_id", "page_number", name="uq_pages_album_page_number"),
    )

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    page_number: Mapped[int] = mapped_column(nullable=False)
    template: Mapped[str] = mapped_column(String(64), default="grid_3", nullable=False)
    html: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    album = relationship("Album", back_populates="pages")
    chapter = relationship("Chapter", back_populates="pages")
    photo_links = relationship("PagePhoto", back_populates="page", cascade="all, delete-orphan")
