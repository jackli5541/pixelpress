from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[3]
PROJECT_DIR = BACKEND_DIR.parent


def _read_env_like_file(file_path: Path) -> dict[str, str]:
    if not file_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cleaned = value.strip().strip("'").strip('"')
        values[key.strip()] = cleaned
    return values


def _collect_external_env_values() -> dict[str, str]:
    merged: dict[str, str] = {}
    for env_file in (PROJECT_DIR / ".env", BACKEND_DIR / ".env"):
        merged.update(_read_env_like_file(env_file))
    merged.update({key: value for key, value in os.environ.items() if value})
    return merged


def _pick_first_non_empty(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return None


def _to_bool(value: object | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseSettings):
    app_name: str = "PixelPress Backend"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    default_book_size: str = "A4_square"
    default_binding: str = "hardcover"
    default_style: str = "minimal"
    story_planner_enabled: bool = False
    story_planner_provider: str = "disabled"
    story_planner_model_name: str | None = None
    story_planner_base_url: str | None = None
    story_planner_api_key: str | None = None
    story_planner_timeout_seconds: int = 20

    @model_validator(mode="before")
    @classmethod
    def hydrate_story_planner_from_env(cls, data: Any) -> Any:
        values = dict(data or {})
        external_env = _collect_external_env_values()

        source = None
        if external_env.get("DEEPSEEK_API_KEY"):
            source = "deepseek"
        elif external_env.get("DASHSCOPE_API_KEY"):
            source = "dashscope"
        elif external_env.get("OPENAI_API_KEY"):
            source = "openai"

        api_key = _pick_first_non_empty(
            values.get("story_planner_api_key"),
            external_env.get("PIXELPRESS_STORY_PLANNER_API_KEY"),
            external_env.get("OPENAI_API_KEY"),
            external_env.get("DEEPSEEK_API_KEY"),
            external_env.get("DASHSCOPE_API_KEY"),
        )

        inferred_base_url = None
        inferred_model_name = None
        if source == "deepseek":
            inferred_base_url = "https://api.deepseek.com/v1"
            inferred_model_name = "deepseek-chat"
        elif source == "dashscope":
            inferred_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            inferred_model_name = "qwen-max"
        elif source == "openai":
            inferred_base_url = "https://api.openai.com/v1"
            inferred_model_name = "gpt-4o-mini"

        provider_base_url = None
        provider_model_name = None
        if source == "deepseek":
            provider_base_url = _pick_first_non_empty(external_env.get("DEEPSEEK_BASE_URL"), inferred_base_url)
            provider_model_name = _pick_first_non_empty(
                external_env.get("DEEPSEEK_MODEL_NAME"),
                external_env.get("DEEPSEEK_MODEL"),
                inferred_model_name,
            )
        elif source == "dashscope":
            provider_base_url = _pick_first_non_empty(external_env.get("DASHSCOPE_BASE_URL"), inferred_base_url)
            provider_model_name = _pick_first_non_empty(
                external_env.get("DASHSCOPE_MODEL_NAME"),
                external_env.get("DASHSCOPE_MODEL"),
                inferred_model_name,
            )
        elif source == "openai":
            provider_base_url = _pick_first_non_empty(external_env.get("OPENAI_BASE_URL"), inferred_base_url)
            provider_model_name = _pick_first_non_empty(
                external_env.get("OPENAI_MODEL_NAME"),
                external_env.get("OPENAI_MODEL"),
                inferred_model_name,
            )

        base_url = _pick_first_non_empty(
            values.get("story_planner_base_url"),
            external_env.get("PIXELPRESS_STORY_PLANNER_BASE_URL"),
            external_env.get("OPENAI_BASE_URL"),
            provider_base_url,
        )
        model_name = _pick_first_non_empty(
            values.get("story_planner_model_name"),
            external_env.get("PIXELPRESS_STORY_PLANNER_MODEL_NAME"),
            external_env.get("OPENAI_MODEL_NAME"),
            external_env.get("OPENAI_MODEL"),
            provider_model_name,
        )
        enabled = _to_bool(
            _pick_first_non_empty(
                values.get("story_planner_enabled"),
                external_env.get("PIXELPRESS_STORY_PLANNER_ENABLED"),
            ),
            default=bool(api_key and base_url and model_name),
        )
        provider = _pick_first_non_empty(
            values.get("story_planner_provider"),
            external_env.get("PIXELPRESS_STORY_PLANNER_PROVIDER"),
            "openai_compatible" if enabled and base_url and model_name else "disabled",
        )

        values["story_planner_api_key"] = api_key
        values["story_planner_base_url"] = base_url
        values["story_planner_model_name"] = model_name
        values["story_planner_enabled"] = enabled
        values["story_planner_provider"] = provider
        return values

    model_config = SettingsConfigDict(
        env_prefix="PIXELPRESS_",
        env_file=(BACKEND_DIR / ".env", PROJECT_DIR / ".env"),
        extra="ignore",
    )


settings = Settings()
