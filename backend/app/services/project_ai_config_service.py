from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ProviderConnectionConfig
from app.core.config import get_settings
from app.repositories.ai_provider_config_repo import AIProviderConfigRepository
from app.repositories.album_repo import AlbumRepository
from app.repositories.project_repo import ProjectRepository
from app.services.project_service import ProjectService
from app.services.secret_service import SecretService
from app.services.default_ai_provider_config_service import DefaultAIProviderConfigService


class ProjectAIConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.project_repo = ProjectRepository(session)
        self.config_repo = AIProviderConfigRepository(session)
        self.secret_service = SecretService()
        self.project_service = ProjectService(session)

    @staticmethod
    def serialize(config) -> dict:
        return {
            "id": config.id,
            "project_id": config.project_id,
            "provider_type": config.provider_type,
            "base_url": config.base_url,
            "model": config.model,
            "api_key_masked": config.api_key_masked,
            "is_active": config.is_active,
            "priority": config.priority,
            "remark": config.remark,
            "created_by_admin_id": config.created_by_admin_id,
            "updated_by_admin_id": config.updated_by_admin_id,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

    async def list_project_configs(self, project_id: str) -> list[dict]:
        return [self.serialize(item) for item in await self.config_repo.list_project_configs(project_id)]

    async def create_config(self, project_id: str, payload: dict, *, admin_user_id: str | None = None) -> dict:
        config = await self.config_repo.create_config(
            {
                "project_id": project_id,
                "provider_type": payload["provider_type"],
                "base_url": payload.get("base_url"),
                "model": payload["model"],
                "api_key_ciphertext": self.secret_service.encrypt_api_key(payload["api_key"]),
                "api_key_masked": self.secret_service.mask_api_key(payload["api_key"]),
                "is_active": payload.get("is_active", True),
                "priority": payload.get("priority", 100),
                "remark": payload.get("remark"),
                "created_by_admin_id": admin_user_id,
                "updated_by_admin_id": admin_user_id,
            }
        )
        await self.session.commit()
        return self.serialize(config)

    async def update_config(self, config_id: str, payload: dict, *, admin_user_id: str | None = None) -> dict | None:
        config = await self.config_repo.get_config(config_id)
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
        updated = await self.config_repo.update_config(config, updates)
        await self.session.commit()
        return self.serialize(updated)

    async def resolve_for_album(self, album_id: str, *, stage: str, model_hint: str | None = None, provider_hint: str | None = None) -> ProviderConnectionConfig:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            raise ValueError("album not found")
        project_id = await self.project_service.ensure_album_project(album)
        if project_id:
            active = await self.config_repo.get_active_config(project_id)
            if active is not None:
                return ProviderConnectionConfig(
                    provider=active.provider_type,
                    api_key=self.secret_service.decrypt_api_key(active.api_key_ciphertext),
                    api_url=active.base_url,
                    model=active.model,
                    source="project_config",
                    config_id=active.id,
                    project_id=project_id,
                )
        default_connection = await DefaultAIProviderConfigService(self.session).resolve(stage)
        if default_connection is not None:
            default_connection.project_id = project_id
            return default_connection
        settings = get_settings()
        return ProviderConnectionConfig(
            provider=provider_hint or "openai_compatible",
            api_key=settings.llm_api_key,
            api_url=settings.llm_api_url,
            model=model_hint or "",
            source="env_fallback",
            config_id=None,
            project_id=project_id,
        )

    async def test_config(self, config_id: str) -> dict | None:
        from app.ai.factory import get_ai_provider
        from app.ai.types import ProviderRequest

        config = await self.config_repo.get_config(config_id)
        if config is None:
            return None
        connection = ProviderConnectionConfig(
            provider=config.provider_type,
            api_key=self.secret_service.decrypt_api_key(config.api_key_ciphertext),
            api_url=config.base_url,
            model=config.model,
            source="project_config",
            config_id=config.id,
            project_id=config.project_id,
        )
        provider = get_ai_provider(connection.provider)
        response = await provider.infer_json(
            ProviderRequest(
                system_prompt="Return a JSON object with {\"status\":\"ok\"}.",
                user_prompt="Respond with a JSON object only.",
                output_schema={"type": "object"},
                model=connection.model,
                connection=connection,
            )
        )
        return {
            "config_id": config.id,
            "provider": response.provider,
            "model": response.model,
            "source": connection.source,
            "debug": response.debug,
            "payload": response.payload,
        }
