from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo


class PhotoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_photos(self, album_id: str) -> list[Photo]:
        result = await self.session.execute(select(Photo).where(Photo.album_id == album_id).order_by(Photo.uploaded_at, Photo.id))
        return list(result.scalars().all())

    async def get_photo(self, album_id: str, photo_id: str) -> Photo | None:
        result = await self.session.execute(
            select(Photo).where(Photo.album_id == album_id, Photo.id == photo_id)
        )
        return result.scalar_one_or_none()

    async def create_photo(self, payload: dict) -> Photo:
        photo = Photo(**payload)
        self.session.add(photo)
        await self.session.flush()
        await self.session.refresh(photo)
        return photo

    async def update_photo(self, photo: Photo, updates: dict) -> Photo:
        for key, value in updates.items():
            setattr(photo, key, value)
        await self.session.flush()
        await self.session.refresh(photo)
        return photo

    async def delete_photo(self, photo: Photo) -> None:
        await self.session.delete(photo)
        await self.session.flush()
