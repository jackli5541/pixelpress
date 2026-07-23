from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.page import Page
from app.models.page_photo import PagePhoto
from app.models.spread import Spread


class SpreadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_spread(self, payload: dict) -> Spread:
        spread = Spread(**payload)
        self.session.add(spread)
        await self.session.flush()
        return spread

    async def list_spreads(self, album_id: str) -> list[Spread]:
        result = await self.session.execute(
            select(Spread)
            .where(Spread.album_id == album_id)
            .options(selectinload(Spread.pages).selectinload(Page.photo_links).selectinload(PagePhoto.photo))
            .order_by(Spread.spread_number, Spread.created_at)
        )
        return list(result.scalars().unique().all())

    async def get_spread(self, album_id: str, spread_id: str) -> Spread | None:
        result = await self.session.execute(
            select(Spread)
            .where(Spread.album_id == album_id, Spread.id == spread_id)
            .options(selectinload(Spread.pages).selectinload(Page.photo_links).selectinload(PagePhoto.photo))
        )
        return result.scalars().unique().one_or_none()

    async def update_spread(self, spread: Spread, updates: dict) -> Spread:
        for key, value in updates.items():
            setattr(spread, key, value)
        await self.session.flush()
        return spread

    async def clear_album_spreads(self, album_id: str) -> None:
        await self.session.execute(delete(Spread).where(Spread.album_id == album_id))
        await self.session.flush()
