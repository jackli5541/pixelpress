from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_provider_config import AIProviderConfig


class AIProviderConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_project_configs(self, project_id: str) -> list[AIProviderConfig]:
        result = await self.session.execute(
            select(AIProviderConfig)
            .where(AIProviderConfig.project_id == project_id)
            .order_by(AIProviderConfig.priority, AIProviderConfig.created_at, AIProviderConfig.id)
        )
        return list(result.scalars().all())

    async def get_config(self, config_id: str) -> AIProviderConfig | None:
        result = await self.session.execute(select(AIProviderConfig).where(AIProviderConfig.id == config_id))
        return result.scalar_one_or_none()

    async def get_active_config(self, project_id: str, stage: str) -> AIProviderConfig | None:
        result = await self.session.execute(
            select(AIProviderConfig)
            .where(AIProviderConfig.project_id == project_id, AIProviderConfig.is_active.is_(True), AIProviderConfig.stage == stage)
            .order_by(AIProviderConfig.priority, AIProviderConfig.created_at, AIProviderConfig.id)
        )
        specific = result.scalars().first()
        if specific is not None:
            return specific
        result = await self.session.execute(
            select(AIProviderConfig)
            .where(AIProviderConfig.project_id == project_id, AIProviderConfig.is_active.is_(True), AIProviderConfig.stage.is_(None))
            .order_by(AIProviderConfig.priority, AIProviderConfig.created_at, AIProviderConfig.id)
        )
        return result.scalars().first()

    async def create_config(self, payload: dict) -> AIProviderConfig:
        config = AIProviderConfig(**payload)
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def update_config(self, config: AIProviderConfig, updates: dict) -> AIProviderConfig:
        for key, value in updates.items():
            setattr(config, key, value)
        await self.session.flush()
        await self.session.refresh(config)
        return config
