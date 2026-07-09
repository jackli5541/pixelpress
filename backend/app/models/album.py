from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Album(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "albums"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    album_type: Mapped[str] = mapped_column(String(64), default="yearbook", nullable=False)
    book_size: Mapped[str] = mapped_column(String(64), default="square_10inch", nullable=False)
    theme_style: Mapped[str] = mapped_column(String(64), default="minimal", nullable=False)
    cover_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    full_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_count: Mapped[int] = mapped_column(default=0, nullable=False)
    print_spec_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    content_revision: Mapped[int] = mapped_column(default=0, nullable=False)
    render_revision: Mapped[int] = mapped_column(default=0, nullable=False)
    preview_html_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    print_html_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    render_manifest_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user = relationship("User", back_populates="albums")
    project = relationship("Project", back_populates="albums")
    photos = relationship("Photo", back_populates="album", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="album", cascade="all, delete-orphan")
    pages = relationship("Page", back_populates="album", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="album", cascade="all, delete-orphan")
    exports = relationship("Export", back_populates="album", cascade="all, delete-orphan")
