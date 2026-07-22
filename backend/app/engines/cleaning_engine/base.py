from __future__ import annotations

from typing import Any, Protocol


class PhotoAnalyzer(Protocol):
    version: str

    def analyze(self, content: bytes, photo_meta: dict[str, Any]) -> dict[str, Any]: ...
