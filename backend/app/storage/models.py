from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StoredFile:
    storage_key: str
    content_type: str
    size: int
    internal_path: str | None = None
    public_url: str | None = None
    width: int | None = None
    height: int | None = None
