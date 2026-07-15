from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_ai_provider
from app.ai.types import ProviderConnectionConfig, ProviderRequest
from app.core.config import get_settings
from app.repositories.default_ai_provider_config_repo import DefaultAIProviderConfigRepository
from app.services.secret_service import SecretService


DEFAULT_STAGES = ("chapter", "layout")


class DefaultAIProviderConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = DefaultAIProviderConfigRepository(session)
        self.secret_service = SecretService()

    @staticmethod
    def serialize(config) -> dict:
        return {
            "id": config.id,
            "stage": config.stage,
            "provider_type": config.provider_type,
            "base_url": config.base_url,
            "model": config.model,
            "api_key_masked": config.api_key_masked,
            "is_active": config.is_active,
            "priority": config.priority,
            "remark": config.remark,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    async def ensure_defaults(self) -> list[dict]:
        settings = get_settings()
        values = {
            "chapter": (settings.ai_provider_b2, settings.ai_model_b2),
            "layout": (settings.ai_provider_b3, settings.ai_model_b3),
        }
        changed = False
        for stage, (provider_type, model) in values.items():
            if await self.repo.get_by_stage(stage):
                continue
            api_key = settings.llm_api_key or ""
            await self.repo.create(
                {
                    "stage": stage,
                    "provider_type": provider_type or "openai_compatible",
                    "base_url": settings.llm_api_url,
                    "model": model or "",
                    "api_key_ciphertext": self.secret_service.encrypt_api_key(api_key),
                    "api_key_masked": self.secret_service.mask_api_key(api_key),
                    "is_active": True,
                    "priority": 100,
                    "remark": "从环境默认配置导入",
                }
            )
            changed = True
        if changed:
            await self.session.commit()
        return [self.serialize(item) for item in await self.repo.list_configs()]

    async def update_config(self, stage: str, payload: dict, *, admin_user_id: str | None = None) -> dict | None:
        if stage not in DEFAULT_STAGES:
            return None
        await self.ensure_defaults()
        config = await self.repo.get_by_stage(stage)
        if config is None:
            return None
        updates = {
            "provider_type": payload.get("provider_type", config.provider_type),
            "base_url": payload.get("base_url", config.base_url),
            "model": payload.get("model", config.model),
            "is_active": payload.get("is_active", config.is_active),
            "priority": payload.get("priority", config.priority),
            "remark": payload.get("remark", config.remark),
            "updated_by_admin_id": admin_user_id,
        }
        if payload.get("api_key"):
            updates["api_key_ciphertext"] = self.secret_service.encrypt_api_key(payload["api_key"])
            updates["api_key_masked"] = self.secret_service.mask_api_key(payload["api_key"])
        updated = await self.repo.update(config, updates)
        await self.session.commit()
        return self.serialize(updated)

    async def resolve(self, stage: str) -> ProviderConnectionConfig | None:
        await self.ensure_defaults()
        config = await self.repo.get_by_stage(stage)
        if config is None or not config.is_active:
            return None
        return ProviderConnectionConfig(
            provider=config.provider_type,
            api_key=self.secret_service.decrypt_api_key(config.api_key_ciphertext),
            api_url=config.base_url,
            model=config.model,
            source="global_default_config",
            config_id=config.id,
        )

    async def test_config(self, stage: str) -> dict | None:
        await self.ensure_defaults()
        config = await self.repo.get_by_stage(stage)
        if config is None:
            return None
        connection = ProviderConnectionConfig(
            provider=config.provider_type,
            api_key=self.secret_service.decrypt_api_key(config.api_key_ciphertext),
            api_url=config.base_url,
            model=config.model,
            source="global_default_config",
            config_id=config.id,
        )
        response = await get_ai_provider(connection.provider).infer_json(
            ProviderRequest(
                system_prompt='Return a JSON object with {"status":"ok"}.',
                user_prompt="Respond with a JSON object only.",
                output_schema={"type": "object"},
                model=connection.model,
                connection=connection,
            )
        )
        return {"config_id": config.id, "stage": stage, "provider": response.provider, "model": response.model, "source": connection.source, "debug": response.debug, "payload": response.payload}
