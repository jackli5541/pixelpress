from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import TaskStatus
from app.models.album import Album
from app.models.task import Task


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_task(self, payload: dict) -> Task:
        task = Task(**payload)
        self.session.add(task)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def update_task(self, task: Task, updates: dict) -> Task:
        for key, value in updates.items():
            setattr(task, key, value)
        await self.session.flush()
        await self.session.refresh(task)
        return task

    async def list_tasks(self, album_id: str | None = None, task_type: str | None = None) -> list[Task]:
        query = select(Task).order_by(Task.created_at.desc(), Task.id.desc())
        if album_id is not None:
            query = query.where(Task.album_id == album_id)
        if task_type is not None:
            query = query.where(Task.task_type == task_type)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_task(self, task_id: str) -> Task | None:
        result = await self.session.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def find_active_task_for_album(self, album_id: str, task_types: list[str] | None = None) -> Task | None:
        query = (
            select(Task)
            .where(Task.album_id == album_id, Task.task_status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]))
            .order_by(Task.created_at.desc(), Task.id.desc())
        )
        if task_types:
            query = query.where(Task.task_type.in_(task_types))
        result = await self.session.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def find_active_by_idempotency_key(self, idempotency_key: str) -> Task | None:
        result = await self.session.execute(
            select(Task)
            .where(
                Task.idempotency_key == idempotency_key,
                Task.task_status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
            )
            .order_by(Task.created_at.desc(), Task.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def claim_queued_task(self, task_id: str, worker_name: str, *, job_id: str | None = None) -> Task | None:
        now = datetime.now(timezone.utc)
        values: dict[str, object] = {
            "task_status": TaskStatus.RUNNING,
            "started_at": now,
            "heartbeat_at": now,
            "worker_name": worker_name,
            "attempt_count": Task.attempt_count + 1,
        }
        if job_id is not None:
            values["job_id"] = job_id
        result = await self.session.execute(
            update(Task)
            .where(Task.id == task_id, Task.task_status == TaskStatus.QUEUED)
            .values(**values)
            .returning(Task.id)
        )
        claimed_id = result.scalar_one_or_none()
        if claimed_id is None:
            return None
        return await self.get_task(task_id)

    async def heartbeat_task(
        self,
        task_id: str,
        *,
        progress_pct: int | None = None,
        progress_step: str | None = None,
        debug_payload: dict | None = None,
    ) -> Task | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        updates: dict[str, object] = {"heartbeat_at": datetime.now(timezone.utc)}
        if progress_pct is not None:
            updates["progress_pct"] = progress_pct
        if progress_step is not None:
            updates["progress_step"] = progress_step
        if debug_payload is not None:
            updates["debug_payload"] = debug_payload
        return await self.update_task(task, updates)

    async def succeed_task(
        self,
        task_id: str,
        *,
        result_payload: dict | None = None,
        debug_payload: dict | None = None,
        metrics_payload: dict | None = None,
        result_revision: int | None = None,
    ) -> Task | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        updates: dict[str, object] = {
            "task_status": TaskStatus.SUCCEEDED,
            "finished_at": datetime.now(timezone.utc),
            "progress_pct": 100,
        }
        if result_payload is not None:
            updates["result_payload"] = result_payload
        if debug_payload is not None:
            updates["debug_payload"] = debug_payload
        if metrics_payload is not None:
            updates["metrics_payload"] = metrics_payload
        if result_revision is not None:
            updates["result_revision"] = result_revision
        return await self.update_task(task, updates)

    async def fail_task(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        fallback_reason: str | None = None,
        debug_payload: dict | None = None,
        metrics_payload: dict | None = None,
    ) -> Task | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        updates: dict[str, object] = {
            "task_status": TaskStatus.FAILED,
            "error_code": error_code,
            "error_message": error_message,
            "retryable": retryable,
            "finished_at": datetime.now(timezone.utc),
        }
        if fallback_reason is not None:
            updates["fallback_reason"] = fallback_reason
        if debug_payload is not None:
            updates["debug_payload"] = debug_payload
        if metrics_payload is not None:
            updates["metrics_payload"] = metrics_payload
        return await self.update_task(task, updates)

    async def request_cancel(self, task_id: str) -> Task | None:
        task = await self.get_task(task_id)
        if task is None:
            return None
        updates: dict[str, object] = {"cancel_requested": True}
        if task.task_status == TaskStatus.QUEUED:
            updates["task_status"] = TaskStatus.CANCELLED
            updates["finished_at"] = datetime.now(timezone.utc)
        return await self.update_task(task, updates)

    async def list_stale_running_tasks(self, timeout_seconds: int) -> list[Task]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        result = await self.session.execute(
            select(Task)
            .where(
                Task.task_status == TaskStatus.RUNNING,
                Task.heartbeat_at.is_not(None),
                Task.heartbeat_at < cutoff,
            )
            .order_by(Task.created_at, Task.id)
        )
        return list(result.scalars().all())

    async def has_active_tasks_for_project(self, project_id: str) -> bool:
        result = await self.session.execute(
            select(Task.id)
            .join(Album, Album.id == Task.album_id)
            .where(
                Album.project_id == project_id,
                Task.task_status.in_([TaskStatus.QUEUED, TaskStatus.RUNNING]),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
