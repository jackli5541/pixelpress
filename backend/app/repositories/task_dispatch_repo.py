from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_dispatch import TaskDispatch


class TaskDispatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_dispatch(self, payload: dict) -> TaskDispatch:
        dispatch = TaskDispatch(**payload)
        self.session.add(dispatch)
        await self.session.flush()
        await self.session.refresh(dispatch)
        return dispatch

    async def get_dispatch(self, dispatch_id: str) -> TaskDispatch | None:
        result = await self.session.execute(select(TaskDispatch).where(TaskDispatch.id == dispatch_id))
        return result.scalar_one_or_none()

    async def list_pending_dispatches(self, limit: int = 100) -> list[TaskDispatch]:
        result = await self.session.execute(
            select(TaskDispatch)
            .where(TaskDispatch.dispatch_status == "pending")
            .order_by(TaskDispatch.created_at, TaskDispatch.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def update_dispatch(self, dispatch: TaskDispatch, updates: dict) -> TaskDispatch:
        for key, value in updates.items():
            setattr(dispatch, key, value)
        await self.session.flush()
        await self.session.refresh(dispatch)
        return dispatch
