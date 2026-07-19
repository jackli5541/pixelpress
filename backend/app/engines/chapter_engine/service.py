"""Dispatch chapter clustering to c7 or the explicit c1 fallback."""

from __future__ import annotations

from typing import Any

from app.engines.chapter_engine.legacy_clusterer import cluster_legacy_photos
from app.engines.chapter_engine.sequential_clusterer import cluster_sequential_photos


def cluster_photos(
    photos: list[dict[str, Any]],
    *,
    mode: str = "embedding",
    theme_context: dict[str, Any] | None = None,
    granularity: int = 0,
) -> list[dict[str, Any]]:
    del mode
    if not photos:
        return []
    if any((photo.get("chapter_features") or {}).get("embedding") for photo in photos):
        strategy = str((theme_context or {}).get("chapter_strategy") or "balanced")
        return cluster_sequential_photos(photos, strategy=strategy, granularity=granularity)
    return cluster_legacy_photos(photos)


__all__ = ["cluster_photos"]
