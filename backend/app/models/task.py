from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_album_status", "album_id", "task_status"),
        Index("ix_tasks_idempotency_key", "idempotency_key"),
        Index("ix_tasks_job_id", "job_id"),
        Index("ix_tasks_status_heartbeat", "task_status", "heartbeat_at"),
    )

    album_id: Mapped[str | None] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), nullable=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    task_status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_revision: Mapped[int | None] = mapped_column(nullable=True)
    result_revision: Mapped[int | None] = mapped_column(nullable=True)
    progress_pct: Mapped[int | None] = mapped_column(nullable=True)
    progress_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pipeline_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    debug_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    album = relationship("Album", back_populates="tasks")
    user = relationship("User", back_populates="tasks")
    exports = relationship("Export", back_populates="task")
    dispatches = relationship("TaskDispatch", back_populates="task", cascade="all, delete-orphan")
