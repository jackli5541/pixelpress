"""Isolated c1 fallback used only when the embedding provider is unavailable."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.engines.chapter_engine.features import (
    clamp,
    haversine_km,
    histogram_similarity,
    parse_datetime,
    photo_sort_key,
    scene_similarity,
    time_range_label,
    valid_coordinate,
)
from app.engines.chapter_engine.representatives import select_representative_photos


LEGACY_ALGORITHM_VERSION = "c1-events-v1"
BOUNDARY_THRESHOLD = 0.45
HARD_GAP_DAYS = 30
SHORT_GAP_HOURS = 2
SHORT_GAP_MAX_DISTANCE_KM = 300.0
UNTIMED_ASSIGN_THRESHOLD = 0.60
UNTIMED_ASSIGN_MARGIN = 0.15


def _linear_score(value: float, points: tuple[tuple[float, float], ...]) -> float:
    if value <= points[0][0]:
        return points[0][1]
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if value <= right_x:
            ratio = (value - left_x) / max(right_x - left_x, 1e-9)
            return left_y + (right_y - left_y) * ratio
    return points[-1][1]


def _time_similarity(left: datetime, right: datetime) -> tuple[float, float]:
    gap_hours = abs((right - left).total_seconds()) / 3600
    score = _linear_score(
        gap_hours,
        ((0.0, 1.0), (6.0, 1.0), (24.0, 0.7), (72.0, 0.3), (336.0, 0.0)),
    )
    return clamp(score), gap_hours


def _gps_similarity(left: dict[str, Any], right: dict[str, Any]) -> tuple[float | None, float | None]:
    left_coordinate = valid_coordinate(left)
    right_coordinate = valid_coordinate(right)
    if left_coordinate is None or right_coordinate is None:
        return None, None
    distance = haversine_km(left_coordinate, right_coordinate)
    score = _linear_score(distance, ((0.0, 1.0), (5.0, 1.0), (50.0, 0.4), (300.0, 0.0)))
    return clamp(score), distance


def _pair_similarity(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_time = parse_datetime(left.get("taken_at"))
    right_time = parse_datetime(right.get("taken_at"))
    components: dict[str, float] = {}
    weights: dict[str, float] = {}
    gap_hours: float | None = None
    if left_time is not None and right_time is not None:
        components["time"], gap_hours = _time_similarity(left_time, right_time)
        weights["time"] = 0.55
    gps_score, distance_km = _gps_similarity(left, right)
    if gps_score is not None:
        components["gps"] = gps_score
        weights["gps"] = 0.25
    scene_score = scene_similarity(left, right)
    if scene_score is not None:
        components["scene"] = scene_score
        weights["scene"] = 0.15
    histogram_score = histogram_similarity(left, right)
    if histogram_score is not None:
        components["histogram"] = histogram_score
        weights["histogram"] = 0.05
    total_weight = sum(weights.values())
    score = sum(components[key] * weights[key] for key in components) / total_weight if total_weight else 0.0
    return {
        "score": round(clamp(score), 4),
        "components": {key: round(value, 4) for key, value in components.items()},
        "gap_hours": round(gap_hours, 3) if gap_hours is not None else None,
        "distance_km": round(distance_km, 3) if distance_km is not None else None,
    }


def _boundary_decision(left: dict[str, Any], right: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    comparison = _pair_similarity(left, right)
    gap_hours = comparison["gap_hours"]
    distance_km = comparison["distance_km"]
    if gap_hours is not None and gap_hours > HARD_GAP_DAYS * 24:
        return True, comparison | {"reason": "large_time_gap", "decision_confidence": 1.0}
    if gap_hours is not None and gap_hours <= SHORT_GAP_HOURS and not (
        distance_km is not None and distance_km > SHORT_GAP_MAX_DISTANCE_KM
    ):
        return False, comparison | {"reason": "short_time_gap", "decision_confidence": 1.0}
    split = comparison["score"] < BOUNDARY_THRESHOLD
    reason = "event_continuity"
    if split:
        if distance_km is not None and distance_km > 50:
            reason = "location_change"
        elif comparison["components"].get("scene", 1.0) < 0.35 or comparison["components"].get("histogram", 1.0) < 0.35:
            reason = "visual_change"
        else:
            reason = "large_time_gap"
    margin = abs(comparison["score"] - BOUNDARY_THRESHOLD)
    confidence = min(1.0, margin / max(BOUNDARY_THRESHOLD, 1 - BOUNDARY_THRESHOLD))
    return split, comparison | {"reason": reason, "decision_confidence": round(confidence, 4)}


def _group_profile_similarity(photo: dict[str, Any], group: list[dict[str, Any]]) -> float | None:
    scores: list[tuple[float, float]] = []
    gps_values = [score for member in group if (score := _gps_similarity(photo, member)[0]) is not None]
    scene_values = [score for member in group if (score := scene_similarity(photo, member)) is not None]
    histogram_values = [score for member in group if (score := histogram_similarity(photo, member)) is not None]
    if gps_values:
        scores.append((max(gps_values), 0.45))
    if scene_values:
        scores.append((max(scene_values), 0.35))
    if histogram_values:
        scores.append((max(histogram_values), 0.20))
    if not scores:
        return None
    weight = sum(item[1] for item in scores)
    return sum(score * score_weight for score, score_weight in scores) / weight


def _suggest_chapter_name(photos: list[dict[str, Any]], index: int = 1) -> str:
    label = time_range_label(photos)
    return f"第{index}章 · {label}" if label != "未知时间" else f"第{index}章"


def _build_chapter(
    photos: list[dict[str, Any]],
    index: int,
    decisions: list[dict[str, Any]],
    reasons: set[str],
    *,
    pending_untimed: bool = False,
) -> dict[str, Any]:
    ordered = sorted(photos, key=photo_sort_key)
    if any(parse_datetime(photo.get("taken_at")) is None for photo in ordered):
        reasons.add("missing_capture_time")
    if pending_untimed:
        reasons.add("weak_assignment")
    time_range = time_range_label(ordered)
    representative_photo_ids = select_representative_photos(ordered)
    return {
        "chapter_key": f"chapter-{index}",
        "name": "待确认照片" if pending_untimed else _suggest_chapter_name(ordered, index),
        "description": "缺少足够信息，请检查照片归属" if pending_untimed else time_range,
        "photo_ids": [str(photo["id"]) for photo in ordered],
        "time_range": time_range,
        "photo_count": len(ordered),
        "segments": [{
            "segment_key": f"chapter-{index}-segment-1",
            "name": "待确认照片" if pending_untimed else "活动阶段 1",
            "description": "缺少足够信息，请检查照片归属" if pending_untimed else time_range,
            "segment_type": "review" if pending_untimed else "event",
            "photo_ids": [str(photo["id"]) for photo in ordered],
            "time_range": time_range,
            "clustering_quality": None,
            "clustering_needs_review": True,
            "clustering_explanation": {
                "reasons": sorted(reasons),
                "boundaries": decisions,
                "representative_photo_ids": representative_photo_ids,
            },
        }],
        "clustering_source": "algorithm",
        "clustering_algorithm_version": LEGACY_ALGORITHM_VERSION,
        "clustering_quality": None,
        "clustering_needs_review": True,
        "clustering_explanation": {
            "representative_photo_ids": representative_photo_ids,
            "naming_source": "rule",
            "fallback": True,
            "fallback_reason": "multimodal_embedding_unavailable",
            "hierarchy": {"chapter_count": 1, "segment_count": 1},
        },
    }


def cluster_legacy_photos(photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not photos:
        return []
    ordered_input = sorted(photos, key=lambda photo: str(photo.get("id") or ""))
    timed = sorted(
        [photo for photo in ordered_input if parse_datetime(photo.get("taken_at")) is not None],
        key=photo_sort_key,
    )
    untimed = [photo for photo in ordered_input if parse_datetime(photo.get("taken_at")) is None]
    if not timed:
        return [_build_chapter(untimed, 1, [], {"missing_capture_time", "weak_assignment"}, pending_untimed=True)]

    groups: list[list[dict[str, Any]]] = [[timed[0]]]
    group_decisions: list[list[dict[str, Any]]] = [[]]
    group_reasons: list[set[str]] = [set()]
    for left, right in zip(timed, timed[1:]):
        split, decision = _boundary_decision(left, right)
        if split:
            group_decisions[-1].append(decision)
            group_reasons[-1].add(str(decision["reason"]))
            groups.append([right])
            group_decisions.append([decision])
            group_reasons.append({str(decision["reason"])})
        else:
            groups[-1].append(right)
            group_decisions[-1].append(decision)

    pending_untimed: list[dict[str, Any]] = []
    for photo in sorted(untimed, key=lambda item: str(item.get("id") or "")):
        available = sorted(
            [
                (score, index)
                for index, group in enumerate(groups)
                if (score := _group_profile_similarity(photo, group)) is not None
            ],
            key=lambda item: (-item[0], item[1]),
        )
        if not available:
            pending_untimed.append(photo)
            continue
        best_score, best_index = available[0]
        runner_up = available[1][0] if len(available) > 1 else 0.0
        if best_score >= UNTIMED_ASSIGN_THRESHOLD and best_score - runner_up >= UNTIMED_ASSIGN_MARGIN:
            groups[best_index].append(photo)
            group_reasons[best_index].add("missing_capture_time")
        else:
            pending_untimed.append(photo)

    chapters = [
        _build_chapter(group, index, group_decisions[index - 1], group_reasons[index - 1])
        for index, group in enumerate(groups, 1)
    ]
    if pending_untimed:
        chapters.append(
            _build_chapter(
                pending_untimed,
                len(chapters) + 1,
                [],
                {"missing_capture_time", "weak_assignment"},
                pending_untimed=True,
            )
        )
    return chapters


__all__ = ["cluster_legacy_photos"]
