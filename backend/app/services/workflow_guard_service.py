from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.task_repo import TaskRepository

LONG_RUNNING_TASK_TYPES = [
    "clean_photos",
    "analyze_album_theme",
    "score_album_theme",
    "cluster_chapters",
    "plan_pages",
    "render_layout",
    "export_html",
    "export_pdf",
]


class WorkflowGuardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.task_repo = TaskRepository(session)

    async def ensure_no_conflicting_active_task(self, album_id: str, *, task_types: list[str] | None = None):
        active = await self.task_repo.find_active_task_for_album(album_id, task_types or LONG_RUNNING_TASK_TYPES)
        return active

    async def acquire_album_guard(self, album_id: str) -> None:
        lock_key = int(album_id.replace("-", "")[:15], 16)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
