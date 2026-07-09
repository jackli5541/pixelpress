from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Chapter(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chapters"

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), default="Untitled", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    order_index: Mapped[int] = mapped_column(default=0, nullable=False)

    album = relationship("Album", back_populates="chapters")
    photo_links = relationship("ChapterPhoto", back_populates="chapter", cascade="all, delete-orphan")
    pages = relationship("Page", back_populates="chapter")
