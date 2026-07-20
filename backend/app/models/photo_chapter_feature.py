from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PhotoChapterFeature(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "photo_chapter_features"
    __table_args__ = (
        UniqueConstraint(
            "photo_id",
            "content_sha256",
            "feature_version",
            "embedding_provider",
            "embedding_model",
            "embedding_dimension",
            name="uq_photo_chapter_feature_cache_key",
        ),
    )

    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
