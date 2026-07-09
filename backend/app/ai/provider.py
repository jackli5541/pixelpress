from __future__ import annotations

from typing import Protocol

from app.ai.types import ProviderRequest, ProviderResponse


class AIProvider(Protocol):
    provider_name: str

    async def infer_json(self, request: ProviderRequest) -> ProviderResponse: ...
