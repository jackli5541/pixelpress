from __future__ import annotations

from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.ai.dashscope_multimodal_embedding_provider import DashScopeMultimodalEmbeddingProvider
from app.ai.provider import AIProvider


def get_ai_provider(provider_name: str) -> AIProvider:
    normalized = (provider_name or "").strip().lower()
    if normalized == "openai_compatible":
        return OpenAICompatibleProvider()
    raise ValueError(f"unsupported ai provider: {provider_name}")


def get_multimodal_embedding_provider(provider_name: str) -> DashScopeMultimodalEmbeddingProvider:
    normalized = (provider_name or "").strip().lower()
    if normalized == "dashscope_multimodal_embedding":
        return DashScopeMultimodalEmbeddingProvider()
    raise ValueError(f"unsupported multimodal embedding provider: {provider_name}")
