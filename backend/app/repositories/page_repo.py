from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from app.models.page import Page
from app.models.page_photo import PagePhoto


class PageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_page(self, payload: dict, photo_ids: list[str], photo_slots: list[dict] | None = None) -> Page:
        page = Page(**payload)
        self.session.add(page)
        await self.session.flush()
        links: list[PagePhoto] = []
        slot_by_id = {str(item["photo_id"]): item for item in (photo_slots or [])}
        for index, photo_id in enumerate(photo_ids):
            slot = slot_by_id.get(str(photo_id), {})
            link = PagePhoto(
                page_id=page.id,
                photo_id=photo_id,
                order_index=index,
                slot_key=slot.get("slot_key"),
                focal_x=float(slot.get("focal_x", 0.5)),
                focal_y=float(slot.get("focal_y", 0.5)),
            )
            self.session.add(link)
            links.append(link)
        await self.session.flush()
        set_committed_value(page, "photo_links", links)
        return page

    async def update_page(
        self,
        page: Page,
        updates: dict,
        photo_ids: list[str] | None = None,
        photo_slots: list[dict] | None = None,
    ) -> Page:
        for key, value in updates.items():
            setattr(page, key, value)
        if photo_ids is not None:
            await self.session.execute(delete(PagePhoto).where(PagePhoto.page_id == page.id))
            links: list[PagePhoto] = []
            slot_by_id = {str(item["photo_id"]): item for item in (photo_slots or [])}
            for index, photo_id in enumerate(photo_ids):
                slot = slot_by_id.get(str(photo_id), {})
                link = PagePhoto(
                    page_id=page.id,
                    photo_id=photo_id,
                    order_index=index,
                    slot_key=slot.get("slot_key"),
                    focal_x=float(slot.get("focal_x", 0.5)),
                    focal_y=float(slot.get("focal_y", 0.5)),
                )
                self.session.add(link)
                links.append(link)
            set_committed_value(page, "photo_links", links)
        await self.session.flush()
        return page

    async def list_pages(self, album_id: str) -> list[Page]:
        result = await self.session.execute(
            select(Page)
            .where(Page.album_id == album_id)
            .options(selectinload(Page.photo_links).selectinload(PagePhoto.photo))
            .order_by(Page.page_number, Page.created_at)
        )
        return list(result.scalars().all())

    async def get_page(self, album_id: str, page_id: str) -> Page | None:
        result = await self.session.execute(
            select(Page)
            .where(Page.album_id == album_id, Page.id == page_id)
            .options(selectinload(Page.photo_links).selectinload(PagePhoto.photo))
        )
        return result.scalar_one_or_none()

    async def delete_page(self, page: Page) -> None:
        await self.session.delete(page)
        await self.session.flush()
