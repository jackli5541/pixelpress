from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.chapter_engine.features import (
    clamp,
    haversine_km,
    parse_datetime,
    photo_sort_key,
    scene_similarity,
    valid_coordinate,
    visual_similarity,
)


MAX_REPRESENTATIVE_PHOTOS = 3
PHASH_NEAR_DUPLICATE_DISTANCE = 8


def _phash_distance(left: dict[str, Any], right: dict[str, Any]) -> int | None:
    left_value = left.get("perceptual_hash")
    right_value = right.get("perceptual_hash")
    if not isinstance(left_value, str) or not isinstance(right_value, str):
        return None
    try:
        return (int(left_value, 16) ^ int(right_value, 16)).bit_count()
    except ValueError:
        return None


def _quality(photo: dict[str, Any]) -> float:
    value = photo.get("quality_score")
    return clamp(float(value) / 10) if isinstance(value, (int, float)) else 0.5


def _metadata_completeness(photo: dict[str, Any]) -> float:
    available = (
        parse_datetime(photo.get("taken_at")) is not None,
        valid_coordinate(photo) is not None,
        bool(photo.get("scene_tags")),
    )
    return sum(available) / len(available)


def _typicality(photo: dict[str, Any], group: list[dict[str, Any]]) -> float:
    values = [score for member in group if member is not photo and (score := visual_similarity(photo, member)) is not None]
    return sum(values) / len(values) if values else 0.5


def _coverage_gain(photo: dict[str, Any], selected: list[dict[str, Any]], group: list[dict[str, Any]]) -> float:
    values: list[float] = []
    photo_time = parse_datetime(photo.get("taken_at"))
    known_times = [value for item in group if (value := parse_datetime(item.get("taken_at"))) is not None]
    selected_times = [value for item in selected if (value := parse_datetime(item.get("taken_at"))) is not None]
    if photo_time is not None and selected_times and len(known_times) > 1:
        span = max((max(known_times) - min(known_times)).total_seconds(), 1)
        nearest = min(abs((photo_time - item).total_seconds()) for item in selected_times)
        values.append(clamp(nearest / span))
    photo_coordinate = valid_coordinate(photo)
    selected_coordinates = [coordinate for item in selected if (coordinate := valid_coordinate(item)) is not None]
    if photo_coordinate is not None and selected_coordinates:
        nearest_km = min(haversine_km(photo_coordinate, item) for item in selected_coordinates)
        values.append(clamp(nearest_km / 300))
    return sum(values) / len(values) if values else 0.5


def select_representative_photos(
    photos: list[dict[str, Any]],
    *,
    limit: int = MAX_REPRESENTATIVE_PHOTOS,
) -> list[str]:
    if not photos or limit <= 0:
        return []
    candidates = sorted(photos, key=photo_sort_key)
    first_ranked = sorted(
        candidates,
        key=lambda photo: (
            -(0.5 * _quality(photo) + 0.3 * _typicality(photo, candidates) + 0.2 * _metadata_completeness(photo)),
            photo_sort_key(photo),
        ),
    )
    selected = [first_ranked[0]]
    while len(selected) < min(limit, len(candidates)):
        ranked: list[tuple[float, tuple[datetime, str], dict[str, Any]]] = []
        for photo in candidates:
            if photo in selected:
                continue
            distances = [_phash_distance(photo, item) for item in selected]
            if any(distance is not None and distance <= PHASH_NEAR_DUPLICATE_DISTANCE for distance in distances):
                continue
            scene_scores = [score for item in selected if (score := scene_similarity(photo, item)) is not None]
            visual_scores = [score for item in selected if (score := visual_similarity(photo, item)) is not None]
            scene_novelty = 1 - max(scene_scores) if scene_scores else 0.5
            visual_difference = 1 - max(visual_scores) if visual_scores else 0.5
            score = (
                0.45 * _quality(photo)
                + 0.25 * scene_novelty
                + 0.15 * _coverage_gain(photo, selected, candidates)
                + 0.15 * visual_difference
            )
            ranked.append((-score, photo_sort_key(photo), photo))
        if not ranked:
            break
        ranked.sort(key=lambda item: (item[0], item[1]))
        selected.append(ranked[0][2])
    return [str(photo["id"]) for photo in selected]
