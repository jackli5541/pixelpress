from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo_chapter_feature import PhotoChapterFeature


class PhotoChapterFeatureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_cached(
        self,
        photo_id: str,
        *,
        content_sha256: str,
        feature_version: str,
        embedding_provider: str,
        embedding_model: str,
        embedding_dimension: int,
    ) -> PhotoChapterFeature | None:
        result = await self.session.execute(
            select(PhotoChapterFeature).where(
                PhotoChapterFeature.photo_id == photo_id,
                PhotoChapterFeature.content_sha256 == content_sha256,
                PhotoChapterFeature.feature_version == feature_version,
                PhotoChapterFeature.embedding_provider == embedding_provider,
                PhotoChapterFeature.embedding_model == embedding_model,
                PhotoChapterFeature.embedding_dimension == embedding_dimension,
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, cached: PhotoChapterFeature | None, payload: dict) -> PhotoChapterFeature:
        if cached is None:
            cached = PhotoChapterFeature(**payload)
            self.session.add(cached)
        else:
            for key, value in payload.items():
                setattr(cached, key, value)
        await self.session.flush()
        await self.session.refresh(cached)
        return cached
