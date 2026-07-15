from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.default_ai_provider_config import DefaultAIProviderConfig


class DefaultAIProviderConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_configs(self) -> list[DefaultAIProviderConfig]:
        result = await self.session.execute(select(DefaultAIProviderConfig).order_by(DefaultAIProviderConfig.stage))
        return list(result.scalars().all())

    async def get_by_stage(self, stage: str) -> DefaultAIProviderConfig | None:
        result = await self.session.execute(select(DefaultAIProviderConfig).where(DefaultAIProviderConfig.stage == stage))
        return result.scalar_one_or_none()

    async def create(self, payload: dict) -> DefaultAIProviderConfig:
        config = DefaultAIProviderConfig(**payload)
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def update(self, config: DefaultAIProviderConfig, updates: dict) -> DefaultAIProviderConfig:
        for key, value in updates.items():
            setattr(config, key, value)
        await self.session.flush()
        await self.session.refresh(config)
        return config
