from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Spread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "spreads"
    __table_args__ = (
        UniqueConstraint("album_id", "spread_number", name="uq_spreads_album_number"),
    )

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id: Mapped[str | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    spread_number: Mapped[int] = mapped_column(nullable=False)
    recipe_key: Mapped[str] = mapped_column(String(64), nullable=False)
    headline: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    planning_version: Mapped[str] = mapped_column(String(64), default="spread-v2", nullable=False)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    album = relationship("Album", back_populates="spreads")
    chapter = relationship("Chapter", back_populates="spreads")
    pages = relationship(
        "Page",
        back_populates="spread",
        cascade="all, delete-orphan",
        order_by="Page.page_number",
    )
