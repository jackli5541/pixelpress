from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Export(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exports"

    album_id: Mapped[str] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    format: Mapped[str] = mapped_column(String(32), default="html", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    album = relationship("Album", back_populates="exports")
    task = relationship("Task", back_populates="exports")
