from __future__ import annotations

from app.db import session as db_session
from app.services.task_dispatch_service import TaskDispatchService


async def dispatch_pending_jobs(limit: int = 100) -> int:
    async with db_session.AsyncSessionFactory() as session:
        service = TaskDispatchService(session)
        count = await service.flush_pending_dispatches(limit)
        await session.commit()
        return count
