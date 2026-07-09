from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_projects(self) -> list[Project]:
        result = await self.session.execute(
            select(Project).options(selectinload(Project.user)).order_by(Project.created_at, Project.id)
        )
        return list(result.scalars().all())

    async def list_user_projects(self, user_id: str) -> list[Project]:
        result = await self.session.execute(
            select(Project).where(Project.user_id == user_id).order_by(Project.created_at, Project.id)
        )
        return list(result.scalars().all())

    async def get_project(self, project_id: str) -> Project | None:
        result = await self.session.execute(
            select(Project).where(Project.id == project_id).options(selectinload(Project.user))
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Project | None:
        result = await self.session.execute(select(Project).where(Project.code == code))
        return result.scalar_one_or_none()

    async def create_project(self, payload: dict) -> Project:
        project = Project(**payload)
        self.session.add(project)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def update_project(self, project: Project, updates: dict) -> Project:
        for key, value in updates.items():
            setattr(project, key, value)
        await self.session.flush()
        await self.session.refresh(project)
        return project

    async def delete_project(self, project: Project) -> None:
        await self.session.delete(project)
        await self.session.flush()
