from __future__ import annotations

from dataclasses import dataclass, field

from pixelpress_backend.models.domain import AlbumState, BookLayout, TaskState, UserOperation


@dataclass
class MemoryStore:
    albums: dict[str, AlbumState] = field(default_factory=dict)
    tasks: dict[str, TaskState] = field(default_factory=dict)
    layouts: dict[str, dict[int, BookLayout]] = field(default_factory=dict)
    operations: dict[str, UserOperation] = field(default_factory=dict)
    idempotency_map: dict[str, str] = field(default_factory=dict)


store = MemoryStore()
