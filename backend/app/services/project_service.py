from __future__ import annotations

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.album import Album
from app.models.project import Project
from app.repositories.album_repo import AlbumRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.task_repo import TaskRepository


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "project"


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = ProjectRepository(session)
        self.album_repo = AlbumRepository(session)
        self.task_repo = TaskRepository(session)

    @staticmethod
    def serialize(project) -> dict:
        return {
            "id": project.id,
            "user_id": project.user_id,
            "username": project.user.username if getattr(project, "user", None) else None,
            "name": project.name,
            "code": project.code,
            "status": project.status,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }

    async def list_projects(self) -> list[dict]:
        return [self.serialize(item) for item in await self.repo.list_projects()]

    async def list_user_projects(self, user_id: str, *, ensure_default: bool = False) -> list[dict]:
        projects = await self.repo.list_user_projects(user_id)
        if not projects and ensure_default:
            await self.ensure_default_project(user_id)
            await self.session.commit()
            projects = await self.repo.list_user_projects(user_id)
        return [self.serialize(item) for item in projects]

    async def create_project(self, payload: dict) -> dict:
        project = await self.repo.create_project(
            {
                "user_id": payload.get("user_id"),
                "name": payload["name"],
                "code": payload.get("code") or await self._next_code(payload["name"]),
                "status": payload.get("status", "active"),
            }
        )
        await self.session.commit()
        project = await self.repo.get_project(project.id)
        return self.serialize(project)

    async def update_project(self, project_id: str, updates: dict) -> dict | None:
        project = await self.repo.get_project(project_id)
        if project is None:
            return None
        updated = await self.repo.update_project(project, updates)
        await self.session.commit()
        updated = await self.repo.get_project(updated.id)
        return self.serialize(updated)

    async def ensure_default_project(self, user_id: str) -> dict:
        existing = await self.repo.list_user_projects(user_id)
        if existing:
            return self.serialize(existing[0])
        project = await self.repo.create_project(
            {
                "user_id": user_id,
                "name": "Default Project",
                "code": await self._next_code(f"default-{user_id[:8]}"),
                "status": "active",
            }
        )
        await self.session.flush()
        return self.serialize(project)

    async def ensure_album_project(self, album: Album) -> str | None:
        if album.project_id or not album.user_id:
            return album.project_id
        project = await self.ensure_default_project(album.user_id)
        await self.album_repo.update_album(album, {"project_id": project["id"]})
        await self.session.flush()
        return project["id"]

    async def user_can_access_project(self, project_id: str, *, user_id: str, is_admin: bool = False) -> bool:
        project = await self.repo.get_project(project_id)
        if project is None:
            return False
        if is_admin:
            return True
        return project.user_id == user_id

    async def delete_project_deep(self, project_id: str, *, user_id: str, is_admin: bool = False) -> dict:
        project = await self.repo.get_project(project_id)
        if project is None:
            raise ValueError("project not found")
        self._assert_project_owner_or_admin(project, user_id=user_id, is_admin=is_admin)
        if await self.task_repo.has_active_tasks_for_project(project_id):
            raise RuntimeError("project has running tasks")

        albums = await self.album_repo.list_albums_by_project(project_id)
        if albums:
            raise RuntimeError("project still contains albums; move or delete those albums first")

        try:
            await self.repo.delete_project(project)
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

        return {
            "project_id": project_id,
            "deleted_album_count": 0,
            "reassigned_album_count": 0,
            "replacement_project_id": None,
        }

    def _assert_project_owner_or_admin(self, project, *, user_id: str, is_admin: bool) -> None:
        if is_admin:
            return
        if project.user_id != user_id:
            raise PermissionError("Forbidden")

    async def _next_code(self, seed: str) -> str:
        base = _slugify(seed)
        candidate = base
        index = 2
        while await self.repo.get_by_code(candidate):
            candidate = f"{base}-{index}"
            index += 1
        return candidate
