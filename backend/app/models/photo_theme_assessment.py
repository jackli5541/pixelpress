from __future__ import annotations

from sqlalchemy import Float, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PhotoThemeAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "photo_theme_assessments"
    __table_args__ = (
        UniqueConstraint("profile_id", "photo_id", name="uq_photo_theme_assessments_profile_photo"),
    )

    profile_id: Mapped[str] = mapped_column(ForeignKey("album_theme_profiles.id", ondelete="CASCADE"), nullable=False)
    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    relevance_label: Mapped[str] = mapped_column(String(32), nullable=False)
    suggested_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    user_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reasons_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scoring_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    profile = relationship("AlbumThemeProfile", back_populates="assessments")
    photo = relationship("Photo")
