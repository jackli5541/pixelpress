from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class CleaningDuplicateMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "cleaning_duplicate_members"
    __table_args__ = (UniqueConstraint("group_id", "photo_id", name="uq_cleaning_group_photo"),)

    group_id: Mapped[str] = mapped_column(ForeignKey("cleaning_duplicate_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    photo_id: Mapped[str] = mapped_column(ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hamming_distance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    burst_time_delta_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_score: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    factors_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    group = relationship("CleaningDuplicateGroup", back_populates="members")
