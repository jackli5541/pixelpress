from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import TaskStatus
from app.repositories.task_dispatch_repo import TaskDispatchRepository
from app.repositories.task_repo import TaskRepository


class TaskDispatchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TaskDispatchRepository(session)
        self.task_repo = TaskRepository(session)

    async def create_dispatch_record(self, *, task_id: str, job_name: str, payload: dict):
        dispatch = await self.repo.create_dispatch(
            {
                "task_id": task_id,
                "job_name": job_name,
                "payload_json": payload,
                "dispatch_status": "pending",
                "attempt_count": 0,
            }
        )
        return dispatch

    async def dispatch_now(self, dispatch_id: str) -> bool:
        dispatch = await self.repo.get_dispatch(dispatch_id)
        if dispatch is None or dispatch.dispatch_status == "dispatched":
            return False
        from app.jobs.enqueue import enqueue_job

        await enqueue_job(job_name=dispatch.job_name, job_id=dispatch.task_id, payload=dispatch.payload_json)
        await self.repo.update_dispatch(
            dispatch,
            {
                "dispatch_status": "dispatched",
                "attempt_count": dispatch.attempt_count + 1,
                "last_error": None,
                "dispatched_at": datetime.now(timezone.utc),
                "available_at": None,
            },
        )
        await self.session.commit()
        return True

    async def mark_dispatch_failed(self, dispatch_id: str, error: str, *, retry_delay_seconds: int = 30) -> None:
        dispatch = await self.repo.get_dispatch(dispatch_id)
        if dispatch is None:
            return
        task = await self.task_repo.get_task(dispatch.task_id)
        next_attempt_count = dispatch.attempt_count + 1
        max_attempts = task.max_attempts if task is not None else 3
        if next_attempt_count >= max_attempts:
            await self.repo.update_dispatch(
                dispatch,
                {
                    "dispatch_status": "failed",
                    "attempt_count": next_attempt_count,
                    "last_error": error,
                    "available_at": None,
                },
            )
            if task is not None and task.task_status == TaskStatus.QUEUED:
                await self.task_repo.fail_task(
                    task.id,
                    error_code="enqueue_failed",
                    error_message=error,
                    retryable=True,
                    metrics_payload={"dispatch_attempts": next_attempt_count},
                )
        else:
            await self.repo.update_dispatch(
                dispatch,
                {
                    "dispatch_status": "pending",
                    "attempt_count": next_attempt_count,
                    "last_error": error,
                    "available_at": datetime.now(timezone.utc) + timedelta(seconds=retry_delay_seconds),
                },
            )
        await self.session.commit()

    async def flush_pending_dispatches(self, limit: int = 100) -> int:
        pending = await self.repo.list_pending_dispatches(limit)
        dispatched_count = 0
        now = datetime.now(timezone.utc)
        for dispatch in pending:
            if dispatch.available_at and dispatch.available_at > now:
                continue
            try:
                ok = await self.dispatch_now(dispatch.id)
                if ok:
                    dispatched_count += 1
            except Exception as exc:  # noqa: BLE001
                await self.mark_dispatch_failed(dispatch.id, str(exc)[:500])
        return dispatched_count
