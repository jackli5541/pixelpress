from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import TaskStatus
from app.core.observability import apply_sentry_context
from app.core.request_context import bind_request_context, get_request_id
from app.repositories.task_repo import TaskRepository
from app.services.serializers import serialize_task
from app.services.workflow_guard_service import LONG_RUNNING_TASK_TYPES, WorkflowGuardService

logger = logging.getLogger(__name__)


def _merge_nested_dict(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any] | None:
    merged: dict[str, Any] = {}
    if isinstance(base, dict):
        merged.update(base)
    if isinstance(extra, dict):
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
    return merged or None


class TaskConflictError(RuntimeError):
    def __init__(self, task: dict) -> None:
        self.task = task
        super().__init__("conflicting active task exists")


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TaskRepository(session)
        self.guard = WorkflowGuardService(session)

    @staticmethod
    def _request_debug_payload() -> dict[str, Any] | None:
        request_id = get_request_id()
        if not request_id:
            return None
        return {"request": {"request_id": request_id, "source": "http"}}

    @staticmethod
    def _request_id_from_debug(debug_payload: dict[str, Any] | None) -> str | None:
        if not isinstance(debug_payload, dict):
            return None
        request = debug_payload.get("request")
        if isinstance(request, dict):
            request_id = request.get("request_id")
            if isinstance(request_id, str) and request_id:
                return request_id
        return None

    @staticmethod
    def _merge_debug_payload(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any] | None:
        return _merge_nested_dict(base, extra)

    @staticmethod
    def _task_log_extra(task: dict[str, Any], **extra: Any) -> dict[str, Any]:
        payload = {
            "task_id": task.get("id"),
            "album_id": task.get("album_id"),
            "task_type": task.get("task_type"),
            "pipeline_name": task.get("pipeline_name"),
            "worker_name": task.get("worker_name"),
            "job_id": task.get("job_id"),
            "stage": task.get("progress_step"),
            "status": task.get("task_status"),
        }
        payload.update({key: value for key, value in extra.items() if value is not None})
        return payload

    def _bind_task_context(self, task: dict[str, Any]) -> None:
        request_id = task.get("request_id") or self._request_id_from_debug(task.get("debug_payload")) or get_request_id()
        bind_request_context(
            request_id=request_id,
            task_id=task.get("id"),
            album_id=task.get("album_id"),
            task_type=task.get("task_type"),
            pipeline_name=task.get("pipeline_name"),
            worker_name=task.get("worker_name"),
            job_id=task.get("job_id"),
            stage=task.get("progress_step"),
        )
        apply_sentry_context()

    async def create_task(self, payload: dict):
        task = await self.repo.create_task(payload)
        await self.session.commit()
        return serialize_task(task)

    async def list_tasks(self, album_id: str | None = None, task_type: str | None = None):
        tasks = await self.repo.list_tasks(album_id, task_type)
        return [serialize_task(task) for task in tasks]

    async def get_task(self, task_id: str):
        task = await self.repo.get_task(task_id)
        if task is None:
            return None
        return serialize_task(task)

    async def get_task_model(self, task_id: str):
        return await self.repo.get_task(task_id)

    async def update_task(self, task_id: str, updates: dict):
        task = await self.repo.get_task(task_id)
        if task is None:
            return None
        updated = await self.repo.update_task(task, updates)
        await self.session.commit()
        return serialize_task(updated)

    async def request_task(
        self,
        *,
        album_id: str,
        user_id: str | None,
        task_type: str,
        task_params: dict | None,
        idempotency_key: str,
        requested_revision: int | None,
        resource_type: str = "album",
        resource_id: str | None = None,
        job_name: str,
        pipeline_name: str,
        pipeline_version: str,
        max_attempts: int | None = None,
    ) -> dict:
        await self.guard.acquire_album_guard(album_id)

        existing = await self.repo.find_active_by_idempotency_key(idempotency_key)
        if existing is not None:
            await self.session.commit()
            serialized = serialize_task(existing)
            self._bind_task_context(serialized)
            logger.info("task request reused active task", extra={"event": "task.requested", **self._task_log_extra(serialized), "idempotency_key": idempotency_key, "result": "existing"})
            return serialized

        conflict = await self.guard.ensure_no_conflicting_active_task(album_id, task_types=LONG_RUNNING_TASK_TYPES)
        if conflict is not None:
            await self.session.commit()
            raise TaskConflictError(serialize_task(conflict))

        request_debug_payload = self._request_debug_payload()
        task = await self.repo.create_task(
            {
                "album_id": album_id,
                "user_id": user_id,
                "task_type": task_type,
                "task_status": TaskStatus.QUEUED,
                "job_id": None,
                "idempotency_key": idempotency_key,
                "task_params": task_params,
                "resource_type": resource_type,
                "resource_id": resource_id or album_id,
                "requested_revision": requested_revision,
                "result_revision": None,
                "progress_pct": 0,
                "progress_step": "queued",
                "attempt_count": 0,
                "max_attempts": max_attempts or 3,
                "started_at": None,
                "heartbeat_at": None,
                "finished_at": None,
                "worker_name": None,
                "retryable": False,
                "error_code": None,
                "error_message": None,
                "fallback_reason": None,
                "cancel_requested": False,
                "pipeline_name": pipeline_name,
                "pipeline_version": pipeline_version,
                "provider": None,
                "model": None,
                "result_payload": None,
                "metrics_payload": None,
                "debug_payload": request_debug_payload,
            }
        )

        from app.services.task_dispatch_service import TaskDispatchService

        dispatch_service = TaskDispatchService(self.session)
        dispatch_payload = {
            "task_id": task.id,
            "album_id": album_id,
            "request_id": self._request_id_from_debug(request_debug_payload) or get_request_id(),
            **(task_params or {}),
        }
        dispatch = await dispatch_service.create_dispatch_record(
            task_id=task.id,
            job_name=job_name,
            payload=dispatch_payload,
        )
        await self.session.commit()
        serialized = serialize_task(task)
        self._bind_task_context(serialized)
        logger.info(
            "task requested",
            extra={
                "event": "task.requested",
                **self._task_log_extra(serialized),
                "idempotency_key": idempotency_key,
                "dispatch_id": dispatch.id,
            },
        )

        try:
            await dispatch_service.dispatch_now(dispatch.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "task dispatch failed",
                extra={
                    "event": "task.dispatch.failed",
                    **self._task_log_extra(serialized),
                    "dispatch_id": dispatch.id,
                    "reason": str(exc)[:500],
                },
            )
            await dispatch_service.mark_dispatch_failed(dispatch.id, str(exc)[:500])
        return serialized

    async def claim_task(self, task_id: str, worker_name: str, *, job_id: str | None = None) -> dict | None:
        task = await self.repo.claim_queued_task(task_id, worker_name, job_id=job_id)
        await self.session.commit()
        if task is None:
            return None
        serialized = serialize_task(task)
        self._bind_task_context(serialized)
        logger.info("task claimed", extra={"event": "task.claimed", **self._task_log_extra(serialized)})
        return serialized

    async def heartbeat(
        self,
        task_id: str,
        *,
        progress_pct: int | None = None,
        progress_step: str | None = None,
        debug_payload: dict | None = None,
    ) -> dict | None:
        task = await self.repo.heartbeat_task(
            task_id,
            progress_pct=progress_pct,
            progress_step=progress_step,
            debug_payload=debug_payload,
        )
        await self.session.commit()
        if task is None:
            return None
        return serialize_task(task)

    async def complete_success(
        self,
        task_id: str,
        *,
        result_payload: dict | None = None,
        debug_payload: dict | None = None,
        metrics_payload: dict | None = None,
        result_revision: int | None = None,
    ) -> dict | None:
        current_task = await self.repo.get_task(task_id)
        request_debug_payload = current_task.debug_payload if current_task is not None else None
        merged_debug_payload = self._merge_debug_payload(request_debug_payload, debug_payload)
        task = await self.repo.succeed_task(
            task_id,
            result_payload=result_payload,
            debug_payload=merged_debug_payload,
            metrics_payload=metrics_payload,
            result_revision=result_revision,
        )
        await self.session.commit()
        if task is None:
            return None
        serialized = serialize_task(task)
        self._bind_task_context(serialized)
        logger.info(
            "task completed",
            extra={
                "event": "task.completed",
                **self._task_log_extra(serialized),
                "duration_ms": (metrics_payload or {}).get("duration_ms") if isinstance(metrics_payload, dict) else None,
            },
        )
        return serialized

    async def complete_failure(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        fallback_reason: str | None = None,
        debug_payload: dict | None = None,
        metrics_payload: dict | None = None,
    ) -> dict | None:
        current_task = await self.repo.get_task(task_id)
        existing_debug_payload = current_task.debug_payload if current_task is not None else None
        merged_debug_payload = self._merge_debug_payload(existing_debug_payload, debug_payload)
        task = await self.repo.fail_task(
            task_id,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            fallback_reason=fallback_reason,
            debug_payload=merged_debug_payload,
            metrics_payload=metrics_payload,
        )
        await self.session.commit()
        if task is None:
            return None
        serialized = serialize_task(task)
        self._bind_task_context(serialized)
        logger.error(
            "task failed",
            extra={
                "event": "task.failed",
                **self._task_log_extra(serialized),
                "error_code": error_code,
                "reason": error_message,
                "duration_ms": (metrics_payload or {}).get("duration_ms") if isinstance(metrics_payload, dict) else None,
                "retryable": retryable,
            },
        )
        return serialized

    async def request_cancel(self, task_id: str) -> dict | None:
        task = await self.repo.request_cancel(task_id)
        await self.session.commit()
        if task is None:
            return None
        serialized = serialize_task(task)
        self._bind_task_context(serialized)
        logger.info("task cancel requested", extra={"event": "task.cancelled", **self._task_log_extra(serialized)})
        return serialized

    async def recover_stale_running_tasks(self) -> int:
        stale_tasks = await self.repo.list_stale_running_tasks(timeout_seconds=600)
        count = 0
        for task in stale_tasks:
            await self.repo.fail_task(
                task.id,
                error_code="worker_stale",
                error_message="worker heartbeat timed out",
                retryable=True,
                metrics_payload={"recovered_at": datetime.now(timezone.utc).isoformat()},
                debug_payload=self._merge_debug_payload(task.debug_payload, {"stage": task.progress_step, "reason": "worker heartbeat timed out"}),
            )
            serialized = serialize_task(task)
            self._bind_task_context(serialized)
            logger.error("stale running task recovered", extra={"event": "task.recovered_stale", **self._task_log_extra(serialized), "error_code": "worker_stale"})
            count += 1
        await self.session.commit()
        return count
