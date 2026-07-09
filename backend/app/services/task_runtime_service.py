from __future__ import annotations

import logging
from typing import Any

from app.common.enums import TaskStatus
from app.core.observability import apply_sentry_context
from app.core.request_context import bind_request_context
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)


class TaskRuntimeService:
    def __init__(self, task_service: TaskService) -> None:
        self.task_service = task_service

    async def ensure_task_not_cancelled(self, task_id: str) -> None:
        task = await self.task_service.get_task_model(task_id)
        if task is None:
            raise ValueError("task not found")
        if task.cancel_requested or task.task_status == TaskStatus.CANCELLED:
            raise RuntimeError("task cancelled")

    async def ensure_revision_matches(self, task_id: str, current_revision: int | None) -> None:
        task = await self.task_service.get_task_model(task_id)
        if task is None:
            raise ValueError("task not found")
        if task.requested_revision is None or current_revision is None:
            return
        if task.requested_revision != current_revision:
            raise RuntimeError("stale task revision")

    async def heartbeat_step(
        self,
        task_id: str,
        step: str,
        pct: int | None = None,
        *,
        debug_payload: dict[str, Any] | None = None,
    ) -> None:
        task = await self.task_service.heartbeat(task_id, progress_pct=pct, progress_step=step, debug_payload=debug_payload)
        if task is None:
            return
        bind_request_context(
            task_id=task.get("id"),
            album_id=task.get("album_id"),
            task_type=task.get("task_type"),
            pipeline_name=task.get("pipeline_name"),
            worker_name=task.get("worker_name"),
            job_id=task.get("job_id"),
            stage=step,
        )
        apply_sentry_context()
        logger.info(
            "task heartbeat updated",
            extra={
                "event": "task.stage.updated",
                "task_id": task.get("id"),
                "album_id": task.get("album_id"),
                "task_type": task.get("task_type"),
                "pipeline_name": task.get("pipeline_name"),
                "worker_name": task.get("worker_name"),
                "job_id": task.get("job_id"),
                "stage": step,
                "progress_pct": pct,
                "status": task.get("task_status"),
            },
        )
