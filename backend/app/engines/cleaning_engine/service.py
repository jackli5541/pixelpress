from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np

from app.engines.cleaning_engine.local_analyzer import LocalPhotoAnalyzer

NEAR_PHASH_THRESHOLD = 6
BURST_PHASH_THRESHOLD = 12
NEAR_ASPECT_THRESHOLD = 0.02
BURST_ASPECT_THRESHOLD = 0.05
NEAR_HISTOGRAM_THRESHOLD = 0.20
BURST_HISTOGRAM_THRESHOLD = 0.30
BURST_WINDOW_MS = 3000
PHASH_BAND_BITS = 5
PHASH_BUCKET_WINDOW = 8
MAX_DUPLICATE_CANDIDATES_PER_PHOTO = 64
MAX_COMPLETE_LINK_CLUSTER_SIZE = 64


def phash_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    return (int(left, 16) ^ int(right, 16)).bit_count()


def histogram_distance(left: list[float] | None, right: list[float] | None) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    return sum(abs(a - b) for a, b in zip(left, right, strict=True)) / 6


def _time_delta_ms(left: Any, right: Any) -> int | None:
    if not isinstance(left, datetime) or not isinstance(right, datetime):
        return None
    return int(abs((left - right).total_seconds()) * 1000)


def _aspect_delta(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = float(left.get("features", {}).get("composition", {}).get("aspect_ratio") or 0)
    b = float(right.get("features", {}).get("composition", {}).get("aspect_ratio") or 0)
    if not a or not b:
        return 1.0
    return abs(a - b) / max(a, b)


def _pair_relation(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any] | None:
    distance = phash_distance(left.get("perceptual_hash"), right.get("perceptual_hash"))
    histogram = histogram_distance(
        left.get("features", {}).get("color_histogram"),
        right.get("features", {}).get("color_histogram"),
    )
    aspect = _aspect_delta(left, right)
    time_delta = _time_delta_ms(left.get("taken_at"), right.get("taken_at"))
    if left.get("content_sha256") and left.get("content_sha256") == right.get("content_sha256"):
        return {"type": "exact", "distance": distance or 0, "histogram_distance": histogram or 0.0, "aspect_delta": aspect, "time_delta_ms": time_delta}
    if distance is None or histogram is None:
        return None
    if distance <= NEAR_PHASH_THRESHOLD and aspect <= NEAR_ASPECT_THRESHOLD and histogram <= NEAR_HISTOGRAM_THRESHOLD:
        return {"type": "near", "distance": distance, "histogram_distance": histogram, "aspect_delta": aspect, "time_delta_ms": time_delta}
    same_device = not left.get("device_model") or not right.get("device_model") or left.get("device_model") == right.get("device_model")
    if (
        time_delta is not None
        and time_delta <= BURST_WINDOW_MS
        and same_device
        and distance <= BURST_PHASH_THRESHOLD
        and aspect <= BURST_ASPECT_THRESHOLD
        and histogram <= BURST_HISTOGRAM_THRESHOLD
    ):
        return {"type": "burst", "distance": distance, "histogram_distance": histogram, "aspect_delta": aspect, "time_delta_ms": time_delta}
    return None


def _candidate_pairs(items: list[dict[str, Any]]) -> set[tuple[int, int]]:
    buckets: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for index, item in enumerate(items):
        phash = item.get("perceptual_hash")
        if not phash:
            continue
        value = int(phash, 16)
        for offset in range(0, 64, PHASH_BAND_BITS):
            width = min(PHASH_BAND_BITS, 64 - offset)
            band = (value >> offset) & ((1 << width) - 1)
            buckets.setdefault((offset, band), []).append((value, index))

    pairs: set[tuple[int, int]] = set()
    candidate_counts = [0] * len(items)

    def add_pair(left: int, right: int) -> None:
        key = (min(left, right), max(left, right))
        if key in pairs:
            return
        left_hash = items[key[0]].get("content_sha256")
        if left_hash and left_hash == items[key[1]].get("content_sha256"):
            return
        if any(candidate_counts[index] >= MAX_DUPLICATE_CANDIDATES_PER_PHOTO for index in key):
            return
        pairs.add(key)
        candidate_counts[key[0]] += 1
        candidate_counts[key[1]] += 1

    for bucket in buckets.values():
        bucket.sort()
        for position, (_, left) in enumerate(bucket):
            for _, right in bucket[position + 1:position + 1 + PHASH_BUCKET_WINDOW]:
                add_pair(left, right)
    return pairs


def _initial_clusters(items: list[dict[str, Any]]) -> list[set[int]]:
    exact_groups: dict[str, set[int]] = {}
    for index, item in enumerate(items):
        content_hash = item.get("content_sha256")
        if content_hash:
            exact_groups.setdefault(content_hash, set()).add(index)

    clusters = [group for group in exact_groups.values() if len(group) >= 2]
    assigned = set().union(*clusters) if clusters else set()
    clusters.extend({index} for index in range(len(items)) if index not in assigned)
    return clusters


def _complete_link_clusters(items: list[dict[str, Any]]) -> list[list[int]]:
    candidate_pairs = _candidate_pairs(items)
    relation_cache: dict[tuple[int, int], dict[str, Any] | None] = {}

    def relation(a: int, b: int) -> dict[str, Any] | None:
        key = (min(a, b), max(a, b))
        if key not in relation_cache:
            relation_cache[key] = _pair_relation(items[key[0]], items[key[1]]) if key in candidate_pairs else None
        return relation_cache[key]

    edges: list[tuple[int, int, int]] = []
    for left, right in candidate_pairs:
        pair = relation(left, right)
        if pair is not None:
            priority = 0 if pair["type"] == "exact" else 1 if pair["type"] == "near" else 2
            edges.append((priority * 100 + int(pair["distance"]), left, right))
    edges.sort()

    clusters = _initial_clusters(items)
    cluster_by_item = {index: cluster for cluster in clusters for index in cluster}
    for _, left, right in edges:
        left_cluster = cluster_by_item[left]
        right_cluster = cluster_by_item[right]
        if left_cluster is right_cluster:
            continue
        if len(left_cluster) + len(right_cluster) > MAX_COMPLETE_LINK_CLUSTER_SIZE:
            continue
        if all(relation(a, b) is not None for a in left_cluster for b in right_cluster):
            left_cluster.update(right_cluster)
            for index in right_cluster:
                cluster_by_item[index] = left_cluster
            right_cluster.clear()
    return [sorted(cluster) for cluster in clusters if len(cluster) >= 2]


class DuplicateGrouper:
    version = "complete-link-v2"

    def group(self, analyses: list[dict[str, Any]]) -> list[list[int]]:
        return _complete_link_clusters(analyses)


def _fallback_analysis(photo_meta: dict[str, Any], version: str) -> dict[str, Any]:
    width = int(photo_meta.get("width") or 0)
    height = int(photo_meta.get("height") or 0)
    min_side = min(width, height) if width and height else 0
    resolution_score = min(1.0, min_side / 1600) if min_side else 0.0
    quality_score = round((0.5 + 0.3 + 0.2 * resolution_score) * 10, 2)
    return {
        "photo_id": photo_meta.get("id"),
        "content_sha256": None,
        "perceptual_hash": None,
        "analysis_version": version,
        "quality_score": quality_score,
        "suggestion": "review",
        "confidence": 0.2,
        "clear_discard": False,
        "hard_reject": False,
        "hard_reject_reason": None,
        "issues": ["analysis_failed"],
        "features": {
            "fallback_used": True,
            "resolution": {"width": width, "height": height, "min_side": min_side, "score": round(resolution_score, 4), "severity": "warning"},
            "composition": {"orientation": "unknown", "aspect_ratio": round(width / height, 5) if height else None},
        },
    }


def fallback_analysis(photo_meta: dict[str, Any], version: str) -> dict[str, Any]:
    return _fallback_analysis(photo_meta, version)


def analyze_photo_quality(photo_meta: dict[str, Any]) -> dict[str, Any]:
    result = _fallback_analysis(photo_meta, "metadata-fallback-v1")
    return {
        "photo_id": result["photo_id"],
        "quality_score": result["quality_score"],
        "tags": [],
        "issues": result["issues"],
        "recommendation": result["suggestion"],
    }


def _preferred_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    resolution = item.get("features", {}).get("resolution", {})
    pixels = int(resolution.get("width") or 0) * int(resolution.get("height") or 0)
    uploaded_at = item.get("uploaded_at")
    uploaded_key = uploaded_at.timestamp() if isinstance(uploaded_at, datetime) else float("inf")
    faces = item.get("features", {}).get("faces", {})
    face_quality = faces.get("aggregate", {})
    return (
        bool(item.get("hard_reject")),
        -int(faces.get("detected_count") or 0),
        -float(face_quality.get("clarity_p20") or 0),
        int(face_quality.get("closed_eye_suspected_count") or 0),
        int(face_quality.get("occlusion_suspected_count") or 0),
        int(face_quality.get("edge_crop_suspected_count") or 0),
        int(face_quality.get("expression_attention_count") or 0),
        -float(item.get("quality_score") or 0),
        -pixels,
        uploaded_key,
        str(item.get("photo_id")),
    )


def _mark_expression_outliers(cluster: list[dict[str, Any]]) -> None:
    samples: list[tuple[dict[str, Any], dict[str, float]]] = []
    for item in cluster:
        faces = item.get("features", {}).get("faces", {}).get("items") or []
        primary = max(faces, key=lambda face: int(face.get("min_side_px") or 0), default=None)
        vector = primary.get("expression_vector") if primary else None
        if vector:
            samples.append((item, vector))
    if len(samples) < 3:
        return
    keys = sorted(set.intersection(*(set(vector) for _, vector in samples)))
    if not keys:
        return
    medians = {key: float(np.median([vector[key] for _, vector in samples])) for key in keys}
    for item, vector in samples:
        deviation = sum(abs(float(vector[key]) - medians[key]) for key in keys) / len(keys)
        if deviation < 0.35:
            continue
        faces = item.get("features", {}).get("faces", {})
        primary = max(faces.get("items") or [], key=lambda face: int(face.get("min_side_px") or 0), default=None)
        if primary is not None:
            primary["expression_attention"] = True
        aggregate = faces.setdefault("aggregate", {})
        aggregate["expression_attention_count"] = int(aggregate.get("expression_attention_count") or 0) + 1
        issues = item.setdefault("issues", [])
        if "expression_attention" not in issues:
            issues.append("expression_attention")


def _build_cleaning_result(
    album_id: str,
    analyses: list[dict[str, Any]],
    *,
    auto_exclude_exact: bool = True,
    auto_exclude_quality: bool = False,
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for item in analyses:
        quality_excluded = bool(auto_exclude_quality and item.get("hard_reject"))
        if item.get("hard_reject"):
            item["suggestion"] = "remove" if quality_excluded else "review"
            item["confidence"] = max(float(item.get("confidence") or 0), 0.99)
        item["auto_excluded"] = quality_excluded
        item["auto_exclusion_source"] = "system_unrecoverable_blur" if quality_excluded else None
    for cluster_indexes in DuplicateGrouper().group(analyses):
        cluster = [analyses[index] for index in cluster_indexes]
        _mark_expression_outliers(cluster)
        ranked = sorted(cluster, key=_preferred_sort_key)
        preferred = ranked[0]
        exact_hashes = [item.get("content_sha256") for item in cluster if item.get("content_sha256")]
        pair_types = {"exact"} if len(exact_hashes) != len(set(exact_hashes)) else set()
        pair_types.update(
            relation["type"]
            for item in cluster
            if item is not preferred and (relation := _pair_relation(preferred, item)) is not None
        )
        group_type = next(iter(pair_types)) if len(pair_types) == 1 else "mixed"
        members: list[dict[str, Any]] = []
        confidence_values: list[float] = []
        exact_canonical: dict[str, dict[str, Any]] = {}
        for item in ranked:
            content_hash = item.get("content_sha256")
            if content_hash and content_hash not in exact_canonical:
                exact_canonical[content_hash] = item
        for rank, item in enumerate(ranked, 1):
            is_preferred = item["photo_id"] == preferred["photo_id"]
            relation = {"type": "preferred", "distance": 0, "time_delta_ms": 0, "histogram_distance": 0.0, "aspect_delta": 0.0}
            if not is_preferred:
                relation = _pair_relation(preferred, item) or relation
            content_hash = item.get("content_sha256")
            exact_copy = bool(content_hash and exact_canonical[content_hash]["photo_id"] != item["photo_id"])
            if exact_copy:
                relation = _pair_relation(exact_canonical[content_hash], item) or relation
            threshold = 1 if relation["type"] == "exact" else NEAR_PHASH_THRESHOLD if relation["type"] == "near" else BURST_PHASH_THRESHOLD
            distance = int(relation.get("distance") or 0)
            confidence_values.append(1.0 if relation["type"] in {"exact", "preferred"} else max(0.0, 1 - distance / max(threshold, 1)))
            if item.get("hard_reject"):
                item["suggestion"] = "remove" if auto_exclude_quality else "review"
                item["confidence"] = max(float(item.get("confidence") or 0), 0.99)
            elif is_preferred:
                item["suggestion"] = "keep"
                item["confidence"] = max(float(item.get("confidence") or 0), 0.95)
            elif exact_copy:
                item["suggestion"] = "remove"
                item["confidence"] = 1.0
            elif relation["type"] == "near" and distance <= 4 and float(relation.get("histogram_distance") or 1) <= 0.10:
                item["suggestion"] = "remove"
                item["confidence"] = 0.9
            else:
                item["suggestion"] = "review"
                item["confidence"] = max(float(item.get("confidence") or 0), 0.75)
            auto_excluded = False
            auto_exclusion_source = None
            if auto_exclude_quality and item.get("hard_reject"):
                auto_excluded = True
                auto_exclusion_source = "system_unrecoverable_blur"
            elif not is_preferred and auto_exclude_exact and exact_copy:
                auto_excluded = True
                auto_exclusion_source = "system_exact_duplicate"
            item["auto_excluded"] = auto_excluded
            item["auto_exclusion_source"] = auto_exclusion_source
            members.append({
                "photo_id": item["photo_id"],
                "relation_type": relation["type"],
                "hamming_distance": distance,
                "burst_time_delta_ms": relation.get("time_delta_ms"),
                "preferred_score": item["quality_score"],
                "rank": rank,
                "is_preferred": is_preferred,
                "auto_excluded": auto_excluded,
                "factors": {
                    "histogram_distance": round(float(relation.get("histogram_distance") or 0), 4),
                    "aspect_delta": round(float(relation.get("aspect_delta") or 0), 4),
                    "sharpness": item.get("features", {}).get("sharpness", {}).get("score"),
                    "exposure": item.get("features", {}).get("exposure", {}).get("score"),
                    "resolution": item.get("features", {}).get("resolution", {}).get("score"),
                },
            })
        groups.append({
            "group_type": group_type,
            "confidence": round(sum(confidence_values) / max(1, len(confidence_values)), 4),
            "preferred_photo_id": preferred["photo_id"],
            "thresholds": {
                "near_phash": NEAR_PHASH_THRESHOLD,
                "burst_phash": BURST_PHASH_THRESHOLD,
                "near_aspect_delta": NEAR_ASPECT_THRESHOLD,
                "burst_window_ms": BURST_WINDOW_MS,
            },
            "explanation": {"algorithm": "complete_link", "member_count": len(members)},
            "members": members,
        })

    summary = {
        "total": len(analyses),
        "analyzed": sum(not item.get("features", {}).get("fallback_used", False) for item in analyses),
        "keep": sum(item["suggestion"] == "keep" for item in analyses),
        "review": sum(item["suggestion"] == "review" for item in analyses),
        "remove": sum(item["suggestion"] == "remove" for item in analyses),
        "auto_excluded": sum(bool(item.get("auto_excluded")) for item in analyses),
        "duplicate_groups": len(groups),
        "analysis_failures": sum(bool(item.get("features", {}).get("fallback_used")) for item in analyses),
    }
    return {"album_id": album_id, "summary": summary, "groups": groups, "per_photo": analyses}


class CleaningDecisionPolicy:
    version = "cleaning-policy-v3"

    def apply(
        self,
        album_id: str,
        analyses: list[dict[str, Any]],
        *,
        auto_exclude_exact: bool = True,
        auto_exclude_quality: bool = False,
    ) -> dict[str, Any]:
        return _build_cleaning_result(
            album_id,
            analyses,
            auto_exclude_exact=auto_exclude_exact,
            auto_exclude_quality=auto_exclude_quality,
        )


def build_cleaning_result(
    album_id: str,
    analyses: list[dict[str, Any]],
    *,
    auto_exclude_exact: bool = True,
    auto_exclude_quality: bool = False,
) -> dict[str, Any]:
    return CleaningDecisionPolicy().apply(
        album_id,
        analyses,
        auto_exclude_exact=auto_exclude_exact,
        auto_exclude_quality=auto_exclude_quality,
    )


def detect_duplicates(photos: list[dict[str, Any]]) -> list[list[str]]:
    analyses = [photo for photo in photos if photo.get("content_sha256") or photo.get("perceptual_hash")]
    return [[analyses[index]["photo_id"] for index in cluster] for cluster in _complete_link_clusters(analyses)]


def run_cleaning(
    album_id: str,
    photo_list: list[dict[str, Any]],
    *,
    version: str = "b1-local-v1",
    auto_exclude_exact: bool = True,
    auto_exclude_quality: bool = False,
) -> dict[str, Any]:
    analyzer = LocalPhotoAnalyzer(version)
    analyses: list[dict[str, Any]] = []
    for photo in photo_list:
        try:
            content = photo.get("content")
            result = analyzer.analyze(content, photo) if isinstance(content, bytes) else _fallback_analysis(photo, version)
        except Exception:
            result = _fallback_analysis(photo, version)
        result.update({"taken_at": photo.get("taken_at"), "device_model": photo.get("device_model"), "uploaded_at": photo.get("uploaded_at")})
        analyses.append(result)
    return build_cleaning_result(
        album_id,
        analyses,
        auto_exclude_exact=auto_exclude_exact,
        auto_exclude_quality=auto_exclude_quality,
    )
