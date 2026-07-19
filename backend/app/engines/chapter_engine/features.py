from __future__ import annotations

from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any


TECHNICAL_SCENE_TAGS = {
    "high_resolution",
    "low_resolution",
    "png_format",
    "jpeg_format",
    "webp_format",
}


def clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y:%m:%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(raw, fmt)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def time_range_label(photos: list[dict[str, Any]]) -> str:
    values = [value for photo in photos if (value := parse_datetime(photo.get("taken_at"))) is not None]
    if not values:
        return "未知时间"
    earliest, latest = min(values), max(values)
    if earliest.date() == latest.date():
        return f"{earliest.year}年{earliest.month}月{earliest.day}日"
    if earliest.year == latest.year and earliest.month == latest.month:
        return f"{earliest.year}年{earliest.month}月{earliest.day}-{latest.day}日"
    if earliest.year == latest.year:
        return f"{earliest.year}年{earliest.month}-{latest.month}月"
    return f"{earliest.year}-{latest.year}"


def valid_coordinate(photo: dict[str, Any]) -> tuple[float, float] | None:
    latitude = photo.get("gps_latitude")
    longitude = photo.get("gps_longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return float(latitude), float(longitude)


def haversine_km(left: tuple[float, float], right: tuple[float, float]) -> float:
    lat1, lon1 = (radians(value) for value in left)
    lat2, lon2 = (radians(value) for value in right)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 6371.0088 * 2 * asin(min(1.0, sqrt(a)))


def scene_similarity(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    left_tags = {
        str(item).strip().lower()
        for item in (left.get("scene_tags") or [])
        if str(item).strip() and str(item).strip().lower() not in TECHNICAL_SCENE_TAGS
    }
    right_tags = {
        str(item).strip().lower()
        for item in (right.get("scene_tags") or [])
        if str(item).strip() and str(item).strip().lower() not in TECHNICAL_SCENE_TAGS
    }
    if not left_tags or not right_tags:
        return None
    return len(left_tags & right_tags) / len(left_tags | right_tags)


def histogram(photo: dict[str, Any]) -> list[float] | None:
    features = photo.get("cleaning_features") or photo.get("features") or {}
    value = features.get("color_histogram") if isinstance(features, dict) else None
    if not isinstance(value, list) or not value:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def histogram_similarity(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    left_histogram = histogram(left)
    right_histogram = histogram(right)
    if left_histogram is None or right_histogram is None or len(left_histogram) != len(right_histogram):
        return None
    channels = 3 if len(left_histogram) % 3 == 0 else 1
    return clamp(sum(min(a, b) for a, b in zip(left_histogram, right_histogram)) / channels)


def visual_similarity(left: dict[str, Any], right: dict[str, Any]) -> float | None:
    """Current visual seam. A future embedding adapter can replace this function."""
    left_embedding = ((left.get("chapter_features") or {}).get("embedding") or [])
    right_embedding = ((right.get("chapter_features") or {}).get("embedding") or [])
    if left_embedding and len(left_embedding) == len(right_embedding):
        try:
            cosine = sum(float(a) * float(b) for a, b in zip(left_embedding, right_embedding))
            return clamp((cosine - 0.2) / 0.75)
        except (TypeError, ValueError):
            pass
    values: list[tuple[float, float]] = []
    scene_score = scene_similarity(left, right)
    histogram_score = histogram_similarity(left, right)
    if scene_score is not None:
        values.append((scene_score, 0.75))
    if histogram_score is not None:
        values.append((histogram_score, 0.25))
    if not values:
        return None
    weight = sum(item[1] for item in values)
    return sum(score * item_weight for score, item_weight in values) / weight


def photo_sort_key(photo: dict[str, Any]) -> tuple[datetime, str]:
    return parse_datetime(photo.get("taken_at")) or datetime.max, str(photo.get("id") or "")
