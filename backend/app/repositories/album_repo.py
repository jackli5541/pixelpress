from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.album import Album
from app.models.chapter import Chapter
from app.models.chapter_photo import ChapterPhoto
from app.models.chapter_segment import ChapterSegment
from app.models.export import Export
from app.models.page import Page
from app.models.page_photo import PagePhoto
from app.models.photo import Photo


class AlbumRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_albums(self, *, user_id: str | None = None, is_admin: bool = False) -> list[Album]:
        query = select(Album).order_by(Album.created_at)
        if not is_admin and user_id:
            query = query.where(Album.user_id == user_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_album(self, payload: dict) -> Album:
        album = Album(**payload)
        self.session.add(album)
        await self.session.flush()
        await self.session.refresh(album)
        return album

    async def get_album(self, album_id: str) -> Album | None:
        result = await self.session.execute(
            select(Album)
            .where(Album.id == album_id)
            .options(selectinload(Album.photos))
        )
        return result.scalar_one_or_none()

    async def get_album_with_assets(self, album_id: str) -> Album | None:
        result = await self.session.execute(
            select(Album)
            .where(Album.id == album_id)
            .options(selectinload(Album.photos), selectinload(Album.exports))
        )
        return result.scalar_one_or_none()

    async def list_albums_by_project(self, project_id: str) -> list[Album]:
        result = await self.session.execute(
            select(Album)
            .where(Album.project_id == project_id)
            .options(selectinload(Album.photos), selectinload(Album.exports))
            .order_by(Album.created_at, Album.id)
        )
        return list(result.scalars().all())

    async def update_album(self, album: Album, updates: dict) -> Album:
        for key, value in updates.items():
            setattr(album, key, value)
        await self.session.flush()
        await self.session.refresh(album)
        return album

    async def reassign_project_albums(self, *, old_project_id: str, new_project_id: str) -> int:
        if old_project_id == new_project_id:
            return 0
        result = await self.session.execute(
            update(Album)
            .where(Album.project_id == old_project_id)
            .values(project_id=new_project_id)
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_album(self, album_id: str) -> None:
        album = await self.get_album(album_id)
        if album is not None:
            await self.session.delete(album)
            await self.session.flush()

    async def summary_counts(self, album_id: str) -> dict[str, int]:
        photo_count = await self.session.scalar(select(func.count(Photo.id)).where(Photo.album_id == album_id))
        chapter_count = await self.session.scalar(select(func.count(Chapter.id)).where(Chapter.album_id == album_id))
        page_count = await self.session.scalar(select(func.count(Page.id)).where(Page.album_id == album_id))
        export_count = await self.session.scalar(select(func.count(Export.id)).where(Export.album_id == album_id))
        return {
            "photo_count": int(photo_count or 0),
            "chapter_count": int(chapter_count or 0),
            "page_count": int(page_count or 0),
            "export_count": int(export_count or 0),
        }

    async def list_exports(self, album_id: str) -> list[Export]:
        result = await self.session.execute(select(Export).where(Export.album_id == album_id).order_by(Export.created_at))
        return list(result.scalars().all())

    async def list_pages(self, album_id: str) -> list[Page]:
        result = await self.session.execute(
            select(Page)
            .where(Page.album_id == album_id)
            .options(selectinload(Page.photo_links).selectinload(PagePhoto.photo))
            .order_by(Page.page_number, Page.created_at)
        )
        return list(result.scalars().all())

    async def list_chapters(self, album_id: str) -> list[Chapter]:
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.album_id == album_id)
            .options(
                selectinload(Chapter.photo_links).selectinload(ChapterPhoto.photo),
                selectinload(Chapter.segments).selectinload(ChapterSegment.photo_links),
            )
            .order_by(Chapter.order_index, Chapter.created_at)
        )
        return list(result.scalars().all())

    async def clear_album_pages(self, album_id: str) -> None:
        await self.session.execute(delete(Page).where(Page.album_id == album_id))
        await self.session.flush()

    async def clear_album_chapters(self, album_id: str) -> None:
        await self.session.execute(delete(Chapter).where(Chapter.album_id == album_id))
        await self.session.flush()
