from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AdminAuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "admin_audit_logs"

    admin_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    admin_user = relationship("User", back_populates="admin_audit_logs")
