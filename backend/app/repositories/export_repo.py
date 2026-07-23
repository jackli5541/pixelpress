from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export import Export


class ExportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_export(self, payload: dict) -> Export:
        export = Export(**payload)
        self.session.add(export)
        await self.session.flush()
        await self.session.refresh(export)
        return export

    async def list_exports(self, album_id: str) -> list[Export]:
        result = await self.session.execute(
            select(Export).where(Export.album_id == album_id).order_by(Export.created_at, Export.id)
        )
        return list(result.scalars().all())

    async def get_export(self, album_id: str, export_id: str) -> Export | None:
        result = await self.session.execute(
            select(Export).where(Export.album_id == album_id, Export.id == export_id)
        )
        return result.scalar_one_or_none()

    async def find_completed(
        self,
        album_id: str,
        *,
        format: str,
        render_revision: int,
        profile_hash: str,
    ) -> Export | None:
        result = await self.session.execute(
            select(Export)
            .where(
                Export.album_id == album_id,
                Export.format == format,
                Export.status == "completed",
                Export.render_revision == render_revision,
                Export.profile_hash == profile_hash,
            )
            .order_by(Export.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
