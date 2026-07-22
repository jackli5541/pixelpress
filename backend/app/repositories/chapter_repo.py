from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.chapter import Chapter
from app.models.chapter_photo import ChapterPhoto
from app.models.chapter_segment import ChapterSegment


class ChapterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_chapter(
        self,
        payload: dict,
        photo_ids: list[str],
        segments: list[dict] | None = None,
    ) -> Chapter:
        chapter = Chapter(**payload)
        self.session.add(chapter)
        await self.session.flush()
        segment_payloads = segments or [{
            "name": payload.get("name", "活动阶段"),
            "description": payload.get("description", ""),
            "segment_type": "legacy",
            "photo_ids": photo_ids,
        }]
        segment_models: list[ChapterSegment] = []
        segment_by_photo: dict[str, str] = {}
        for index, segment_payload in enumerate(segment_payloads):
            segment_data = {
                key: value
                for key, value in segment_payload.items()
                if key not in {"photo_ids", "segment_key"}
            }
            segment_data.update({"chapter_id": chapter.id, "order_index": index})
            segment = ChapterSegment(**segment_data)
            self.session.add(segment)
            await self.session.flush()
            segment_models.append(segment)
            for photo_id in segment_payload.get("photo_ids", []):
                segment_by_photo[str(photo_id)] = segment.id
        links: list[ChapterPhoto] = []
        for index, photo_id in enumerate(photo_ids):
            link = ChapterPhoto(
                chapter_id=chapter.id,
                photo_id=photo_id,
                segment_id=segment_by_photo.get(str(photo_id)),
                order_index=index,
            )
            self.session.add(link)
            links.append(link)
        await self.session.flush()
        set_committed_value(chapter, "photo_links", links)
        set_committed_value(chapter, "segments", segment_models)
        for segment in segment_models:
            set_committed_value(
                segment,
                "photo_links",
                [link for link in links if link.segment_id == segment.id],
            )
        return chapter

    async def update_chapter(self, chapter: Chapter, updates: dict, photo_ids: list[str] | None = None) -> Chapter:
        for key, value in updates.items():
            setattr(chapter, key, value)
        if photo_ids is not None:
            await self.session.execute(delete(ChapterPhoto).where(ChapterPhoto.chapter_id == chapter.id))
            await self.session.execute(delete(ChapterSegment).where(ChapterSegment.chapter_id == chapter.id))
            default_segment = ChapterSegment(
                chapter_id=chapter.id,
                name=chapter.name,
                description=chapter.description,
                order_index=0,
                segment_type="manual",
            )
            self.session.add(default_segment)
            await self.session.flush()
            links: list[ChapterPhoto] = []
            for index, photo_id in enumerate(photo_ids):
                link = ChapterPhoto(
                    chapter_id=chapter.id,
                    photo_id=photo_id,
                    segment_id=default_segment.id,
                    order_index=index,
                )
                self.session.add(link)
                links.append(link)
            set_committed_value(chapter, "photo_links", links)
            set_committed_value(chapter, "segments", [default_segment])
            set_committed_value(default_segment, "photo_links", links)
        await self.session.flush()
        return chapter

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

    async def get_chapter(self, album_id: str, chapter_id: str) -> Chapter | None:
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.album_id == album_id, Chapter.id == chapter_id)
            .options(
                selectinload(Chapter.photo_links).selectinload(ChapterPhoto.photo),
                selectinload(Chapter.segments).selectinload(ChapterSegment.photo_links),
            )
        )
        return result.scalar_one_or_none()

    async def delete_chapter(self, chapter: Chapter) -> None:
        await self.session.delete(chapter)
        await self.session.flush()
