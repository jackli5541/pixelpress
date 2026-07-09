from __future__ import annotations

from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.ai.provider import AIProvider


def get_ai_provider(provider_name: str) -> AIProvider:
    normalized = (provider_name or "").strip().lower()
    if normalized == "openai_compatible":
        return OpenAICompatibleProvider()
    raise ValueError(f"unsupported ai provider: {provider_name}")
