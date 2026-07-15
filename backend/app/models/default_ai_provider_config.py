from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DefaultAIProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "default_ai_provider_configs"
    __table_args__ = (UniqueConstraint("stage", name="uq_default_ai_provider_configs_stage"),)

    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    api_key_ciphertext: Mapped[str] = mapped_column(Text(), nullable=False)
    api_key_masked: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_by_admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_admin_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
