from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.chapter import Chapter
from app.models.chapter_photo import ChapterPhoto


class ChapterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_chapter(self, payload: dict, photo_ids: list[str]) -> Chapter:
        chapter = Chapter(**payload)
        self.session.add(chapter)
        await self.session.flush()
        links: list[ChapterPhoto] = []
        for index, photo_id in enumerate(photo_ids):
            link = ChapterPhoto(chapter_id=chapter.id, photo_id=photo_id, order_index=index)
            self.session.add(link)
            links.append(link)
        await self.session.flush()
        set_committed_value(chapter, "photo_links", links)
        return chapter

    async def update_chapter(self, chapter: Chapter, updates: dict, photo_ids: list[str] | None = None) -> Chapter:
        for key, value in updates.items():
            setattr(chapter, key, value)
        if photo_ids is not None:
            await self.session.execute(delete(ChapterPhoto).where(ChapterPhoto.chapter_id == chapter.id))
            links: list[ChapterPhoto] = []
            for index, photo_id in enumerate(photo_ids):
                link = ChapterPhoto(chapter_id=chapter.id, photo_id=photo_id, order_index=index)
                self.session.add(link)
                links.append(link)
            set_committed_value(chapter, "photo_links", links)
        await self.session.flush()
        return chapter

    async def list_chapters(self, album_id: str) -> list[Chapter]:
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.album_id == album_id)
            .options(selectinload(Chapter.photo_links))
            .order_by(Chapter.order_index, Chapter.created_at)
        )
        return list(result.scalars().all())

    async def get_chapter(self, album_id: str, chapter_id: str) -> Chapter | None:
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.album_id == album_id, Chapter.id == chapter_id)
            .options(selectinload(Chapter.photo_links))
        )
        return result.scalar_one_or_none()

    async def delete_chapter(self, chapter: Chapter) -> None:
        await self.session.delete(chapter)
        await self.session.flush()
