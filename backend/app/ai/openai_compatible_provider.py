from __future__ import annotations

import json
import time
from typing import Any

import httpx

from app.ai.types import ProviderRequest, ProviderResponse
from app.core.config import get_settings


class AIProviderError(RuntimeError):
    pass


class OpenAICompatibleProvider:
    provider_name = "openai_compatible"

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.llm_api_key
        self.api_url = settings.llm_api_url
        self.timeout_seconds = settings.ai_request_timeout_seconds
        self.max_retries = settings.ai_provider_max_retries

    async def infer_json(self, request: ProviderRequest) -> ProviderResponse:
        api_key = request.connection.api_key if request.connection else self.api_key
        api_url = request.connection.api_url if request.connection else self.api_url
        model = request.connection.model if request.connection and request.connection.model else request.model
        if not api_key or not api_url:
            raise AIProviderError("OpenAI-compatible API is not configured")

        endpoint = self._normalize_endpoint(api_url)
        payload = {
            "model": model,
            "temperature": request.response_temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            started_at = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                    response.raise_for_status()
                    response_json = response.json()
                raw_text = self._extract_content(response_json)
                parsed_payload = json.loads(raw_text)
                elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
                return ProviderResponse(
                    payload=parsed_payload,
                    raw_text=raw_text,
                    model=model,
                    provider=self.provider_name,
                    debug={
                        "endpoint": endpoint,
                        "attempt": attempt + 1,
                        "elapsed_ms": elapsed_ms,
                        "response_id": response_json.get("id"),
                        "source": request.connection.source if request.connection else "settings",
                        "config_id": request.connection.config_id if request.connection else None,
                        "project_id": request.connection.project_id if request.connection else None,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc

        raise AIProviderError(f"provider request failed: {last_error}") from last_error

    @staticmethod
    def _normalize_endpoint(api_url: str) -> str:
        trimmed = api_url.rstrip("/")
        if trimmed.endswith("/chat/completions"):
            return trimmed
        if trimmed.endswith("/v1"):
            return f"{trimmed}/chat/completions"
        return f"{trimmed}/v1/chat/completions"

    @staticmethod
    def _extract_content(response_json: dict[str, Any]) -> str:
        choices = response_json.get("choices") or []
        if not choices:
            raise AIProviderError("provider response did not include choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [item.get("text", "") for item in content if isinstance(item, dict)]
            text = "".join(parts).strip()
            if text:
                return text
        raise AIProviderError("provider response did not include text content")
