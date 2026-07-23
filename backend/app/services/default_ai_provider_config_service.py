from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_ai_provider
from app.ai.factory import get_multimodal_embedding_provider
from app.ai.types import ImageEmbeddingRequest, ImagePayload, ProviderConnectionConfig, ProviderRequest
from app.core.config import get_settings
from app.repositories.default_ai_provider_config_repo import DefaultAIProviderConfigRepository
from app.services.secret_service import SecretService


DEFAULT_STAGES = ("chapter", "chapter_embedding", "layout")
STAGE_PROVIDERS = {
    "chapter": {"openai_compatible"},
    "chapter_embedding": {"dashscope_multimodal_embedding"},
    "layout": {"openai_compatible"},
}


def validate_stage_provider(stage: str, provider_type: str) -> None:
    if stage not in DEFAULT_STAGES or provider_type not in STAGE_PROVIDERS[stage]:
        raise ValueError(f"unsupported provider for {stage}: {provider_type}")


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
            "chapter": settings.resolved_chapter_config,
            "chapter_embedding": settings.resolved_embedding_config,
            "layout": settings.resolved_layout_config,
        }
        changed = False
        for stage, (provider_type, base_url, api_key, model) in values.items():
            existing = await self.repo.get_by_stage(stage)
            inherited_embedding_key = settings.resolved_embedding_config[2] or ""
            if existing:
                updates = {}
                # Defaults are seeded before an operator may add backend/.env.
                # Keep those env-seeded defaults synchronized, while an admin
                # edit remains authoritative once it has an audit actor.
                is_env_seeded = existing.created_by_admin_id is None and existing.updated_by_admin_id is None
                if is_env_seeded and provider_type and existing.provider_type != provider_type:
                    updates["provider_type"] = provider_type
                if (is_env_seeded or not existing.base_url) and base_url and existing.base_url != base_url:
                    updates["base_url"] = base_url
                if (is_env_seeded or not existing.model) and model and existing.model != model:
                    updates["model"] = model
                if api_key and (is_env_seeded or not existing.api_key_masked) and existing.api_key_masked != self.secret_service.mask_api_key(api_key):
                    updates["api_key_ciphertext"] = self.secret_service.encrypt_api_key(api_key)
                    updates["api_key_masked"] = self.secret_service.mask_api_key(api_key)
                if updates:
                    await self.repo.update(existing, updates)
                    changed = True
                continue
            api_key = api_key or ""
            await self.repo.create(
                {
                    "stage": stage,
                    "provider_type": provider_type or "openai_compatible",
                    "base_url": base_url,
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
        provider_type = payload.get("provider_type", config.provider_type)
        validate_stage_provider(stage, provider_type)
        updates = {
            "provider_type": provider_type,
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
        if stage == "chapter_embedding":
            response = await get_multimodal_embedding_provider(connection.provider).embed_images(
                ImageEmbeddingRequest(
                    images=[ImagePayload(media_type="image/jpeg", data_base64=self._test_image_base64())],
                    model=connection.model,
                    dimension=get_settings().chapter_embedding_dimension,
                    connection=connection,
                )
            )
            return {
                "config_id": config.id,
                "stage": stage,
                "provider": response.provider,
                "model": response.model,
                "source": connection.source,
                "debug": response.debug,
                "payload": {"status": "ok", "dimension": len(response.embeddings[0])},
            }
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

    @staticmethod
    def _test_image_base64() -> str:
        output = BytesIO()
        Image.new("RGB", (64, 64), color=(64, 128, 192)).save(output, format="JPEG", quality=85)
        return base64.b64encode(output.getvalue()).decode("ascii")
