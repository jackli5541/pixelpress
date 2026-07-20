from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from math import ceil, sqrt
from typing import Any

import numpy as np
from sklearn.metrics import silhouette_samples

from app.engines.chapter_engine.features import histogram, haversine_km, parse_datetime, time_range_label, valid_coordinate
from app.engines.chapter_engine.representatives import select_representative_photos


ALGORITHM_VERSION = "c7-embedding-sequential-v1"
REFERENCE_RUNS = 20
STABILITY_RUNS = 20
QUALITY_REVIEW_THRESHOLD = 0.60
COVERAGE_REVIEW_THRESHOLD = 0.50
K_STABILITY_REVIEW_THRESHOLD = 0.60

STRATEGY_WEIGHTS: dict[str, dict[str, float]] = {
    "balanced": {"embedding": 0.60, "time": 0.20, "gps": 0.10, "color": 0.10},
    "activity_first": {"embedding": 0.75, "time": 0.10, "gps": 0.05, "color": 0.10},
    "time_first": {"embedding": 0.40, "time": 0.45, "gps": 0.10, "color": 0.05},
    "location_first": {"embedding": 0.40, "time": 0.10, "gps": 0.45, "color": 0.05},
}
SEGMENT_WEIGHTS = {"embedding": 0.75, "time": 0.10, "gps": 0.05, "color": 0.10}


@dataclass(frozen=True, slots=True)
class FeatureRow:
    photo: dict[str, Any]
    original_index: int
    taken_at: datetime | None
    embedding: np.ndarray | None
    coordinate: tuple[float, float] | None
    color: np.ndarray | None


@dataclass(frozen=True, slots=True)
class ClusterSelection:
    labels: np.ndarray
    auto_selected_k: int
    selected_k: int
    peak_k: int
    gaps: tuple[float, ...]
    standard_errors: tuple[float, ...]
    max_clusters: int


@dataclass(frozen=True, slots=True)
class StabilityResult:
    boundaries: tuple[float, ...]
    k_selection_stability: float
    auto_k_values: tuple[int, ...]


def _normalized_vector(value: Any) -> np.ndarray | None:
    if not isinstance(value, list) or not value:
        return None
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if vector.ndim != 1 or not np.all(np.isfinite(vector)):
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else None


def _feature_row(photo: dict[str, Any], index: int) -> FeatureRow:
    chapter_features = photo.get("chapter_features") or {}
    color_value = histogram(photo)
    color = np.asarray(color_value, dtype=np.float64) if color_value else None
    if color is not None:
        total = float(color.sum())
        color = color / total if total > 0 else None
    return FeatureRow(
        photo=photo,
        original_index=index,
        taken_at=parse_datetime(photo.get("taken_at")),
        embedding=_normalized_vector(chapter_features.get("embedding")),
        coordinate=valid_coordinate(photo),
        color=color,
    )


def _robust_scale(values: list[float]) -> float:
    finite = np.asarray([value for value in values if np.isfinite(value)], dtype=np.float64)
    positive = finite[finite > 0]
    if not len(positive):
        return 1.0
    q25, q75 = np.percentile(positive, [25, 75])
    return max(float(q75 - q25), float(np.median(positive)), 1e-9)


def _cosine_distance(left: np.ndarray | None, right: np.ndarray | None) -> float | None:
    if left is None or right is None or left.shape != right.shape:
        return None
    return float(np.clip((1.0 - float(np.dot(left, right))) / 2.0, 0.0, 1.0))


def _hellinger_distance(left: np.ndarray | None, right: np.ndarray | None) -> float | None:
    if left is None or right is None or left.shape != right.shape:
        return None
    return float(np.linalg.norm(np.sqrt(left) - np.sqrt(right)) / sqrt(2.0))


def _channel_scales(rows: list[FeatureRow]) -> tuple[float, float]:
    time_values = [
        abs((right.taken_at - left.taken_at).total_seconds())
        for index, left in enumerate(rows)
        for right in rows[index + 1 :]
        if left.taken_at is not None and right.taken_at is not None
    ]
    gps_values = [
        haversine_km(left.coordinate, right.coordinate)
        for index, left in enumerate(rows)
        for right in rows[index + 1 :]
        if left.coordinate is not None and right.coordinate is not None
    ]
    return _robust_scale(time_values), _robust_scale(gps_values)


def distance_matrix(
    rows: list[FeatureRow],
    weights: dict[str, float],
    *,
    include_time: bool = True,
) -> tuple[np.ndarray, dict[str, float]]:
    count = len(rows)
    matrix = np.zeros((count, count), dtype=np.float64)
    available_counts = {channel: 0 for channel in weights}
    pair_count = count * (count - 1) // 2
    time_scale, gps_scale = _channel_scales(rows)
    for left_index in range(count):
        for right_index in range(left_index + 1, count):
            left, right = rows[left_index], rows[right_index]
            components: dict[str, float] = {}
            embedding = _cosine_distance(left.embedding, right.embedding)
            color = _hellinger_distance(left.color, right.color)
            if embedding is not None:
                components["embedding"] = embedding
            if include_time and left.taken_at is not None and right.taken_at is not None:
                gap = abs((right.taken_at - left.taken_at).total_seconds())
                components["time"] = gap / (gap + time_scale)
            if left.coordinate is not None and right.coordinate is not None:
                gap = haversine_km(left.coordinate, right.coordinate)
                components["gps"] = gap / (gap + gps_scale)
            if color is not None:
                components["color"] = color
            available_weight = sum(weights[channel] for channel in components)
            value = (
                sum(weights[channel] * component for channel, component in components.items()) / available_weight
                if available_weight else 1.0
            )
            matrix[left_index, right_index] = matrix[right_index, left_index] = float(np.clip(value, 0.0, 1.0))
            for channel in components:
                available_counts[channel] += 1
    coverage = {
        channel: round(available_counts[channel] / pair_count, 4) if pair_count else float(bool(count))
        for channel in weights
    }
    return matrix, coverage


def _cluster(matrix: np.ndarray, cluster_count: int) -> np.ndarray:
    count = len(matrix)
    if count == 0:
        return np.asarray([], dtype=np.int32)
    if cluster_count <= 1 or count == 1:
        return np.zeros(count, dtype=np.int32)
    return _cluster_candidates(matrix, [min(cluster_count, count)])[min(cluster_count, count)]


def _interval_costs(matrix: np.ndarray) -> np.ndarray:
    count = len(matrix)
    prefix = np.pad(matrix, ((1, 0), (1, 0))).cumsum(axis=0).cumsum(axis=1)
    costs = np.zeros((count, count), dtype=np.float64)
    for start in range(count):
        for end in range(start + 1, count + 1):
            size = end - start
            block_sum = prefix[end, end] - prefix[start, end] - prefix[end, start] + prefix[start, start]
            costs[start, end - 1] = float(block_sum) / (2.0 * size) if size > 1 else 0.0
    return costs


def _cluster_candidates(matrix: np.ndarray, candidates: list[int]) -> dict[int, np.ndarray]:
    count = len(matrix)
    if count <= 1:
        return {value: np.zeros(count, dtype=np.int32) for value in candidates}
    max_clusters = min(max(candidates), count)
    costs = _interval_costs(matrix)
    objectives = np.full((max_clusters + 1, count + 1), np.inf, dtype=np.float64)
    previous = np.full((max_clusters + 1, count + 1), -1, dtype=np.int32)
    objectives[0, 0] = 0.0
    for cluster_count in range(1, max_clusters + 1):
        for end in range(cluster_count, count + 1):
            starts = np.arange(cluster_count - 1, end)
            values = objectives[cluster_count - 1, starts] + costs[starts, end - 1]
            selected_index = int(np.argmin(values))
            objectives[cluster_count, end] = values[selected_index]
            previous[cluster_count, end] = int(starts[selected_index])
    results: dict[int, np.ndarray] = {}
    for cluster_count in candidates:
        resolved_count = min(cluster_count, count)
        spans: list[tuple[int, int]] = []
        end = count
        for step in range(resolved_count, 0, -1):
            start = int(previous[step, end])
            spans.append((start, end))
            end = start
        labels = np.zeros(count, dtype=np.int32)
        for label, (start, end) in enumerate(reversed(spans)):
            labels[start:end] = label
        results[cluster_count] = labels
    return results


def _dispersion(matrix: np.ndarray, labels: np.ndarray) -> float:
    total = 0.0
    for label in sorted(set(int(value) for value in labels)):
        indices = np.flatnonzero(labels == label)
        if len(indices) > 1:
            block = matrix[np.ix_(indices, indices)]
            total += float(block.sum()) / (2.0 * len(indices))
    return max(total, 1e-12)


def _pca_sample_batch(
    values: list[np.ndarray | None],
    rng: np.random.Generator,
    sample_count: int,
    *,
    normalize: bool,
) -> list[list[np.ndarray | None]]:
    available = [index for index, value in enumerate(values) if value is not None]
    if not available:
        return [[None for _ in values] for _ in range(sample_count)]
    matrix = np.stack([values[index] for index in available])
    mean = matrix.mean(axis=0)
    centered = matrix - mean
    if len(matrix) > 1 and np.any(np.abs(centered) > 1e-12):
        _, _, components = np.linalg.svd(centered, full_matrices=False)
        scores = centered @ components.T
        lower, upper = scores.min(axis=0), scores.max(axis=0)
    else:
        components = None
        lower = upper = None
    outputs: list[list[np.ndarray | None]] = []
    for _ in range(sample_count):
        sampled = (
            rng.uniform(lower, upper, size=scores.shape) @ components + mean
            if components is not None else matrix.copy()
        )
        output: list[np.ndarray | None] = [None for _ in values]
        for sample_index, row_index in enumerate(available):
            vector = sampled[sample_index]
            if normalize:
                norm = float(np.linalg.norm(vector))
                vector = vector / norm if norm > 0 else matrix[sample_index]
            else:
                vector = np.clip(vector, 0.0, None)
                total = float(vector.sum())
                vector = vector / total if total > 0 else matrix[sample_index]
            output[row_index] = vector
        outputs.append(output)
    return outputs


def _reference_samples(rows: list[FeatureRow], *, seed: int, sample_count: int) -> list[list[FeatureRow]]:
    rng = np.random.default_rng(seed)
    embeddings = _pca_sample_batch([row.embedding for row in rows], rng, sample_count, normalize=True)
    colors = _pca_sample_batch([row.color for row in rows], rng, sample_count, normalize=False)
    known_times = [row.taken_at for row in rows if row.taken_at is not None]
    coordinates = [row.coordinate for row in rows if row.coordinate is not None]
    samples: list[list[FeatureRow]] = []
    for sample_index in range(sample_count):
        generated_times: list[datetime] = []
        if known_times:
            start, end = min(known_times), max(known_times)
            generated_times = [
                start + (end - start) * float(value)
                for value in np.sort(rng.uniform(0, 1, len(known_times)))
            ]
        generated_coordinates: list[tuple[float, float]] = []
        if coordinates:
            latitudes = [value[0] for value in coordinates]
            longitudes = [value[1] for value in coordinates]
            generated_coordinates = list(zip(
                rng.uniform(min(latitudes), max(latitudes), len(coordinates)),
                rng.uniform(min(longitudes), max(longitudes), len(coordinates)),
            ))
        time_index = 0
        coordinate_index = 0
        reference = []
        for row_index, row in enumerate(rows):
            taken_at = None
            if row.taken_at is not None:
                taken_at = generated_times[time_index]
                time_index += 1
            coordinate = None
            if row.coordinate is not None:
                coordinate = generated_coordinates[coordinate_index]
                coordinate_index += 1
            reference.append(replace(
                row,
                taken_at=taken_at,
                embedding=embeddings[sample_index][row_index],
                coordinate=coordinate,
                color=colors[sample_index][row_index],
            ))
        samples.append(reference)
    return samples


def _select_from_gap(gaps: list[float], errors: list[float], candidates: list[int]) -> tuple[int, int]:
    peak_index = int(np.argmax(gaps))
    selected = next((
        candidate
        for index, candidate in enumerate(candidates)
        if gaps[peak_index] - gaps[index] <= sqrt(errors[peak_index] ** 2 + errors[index] ** 2)
    ), candidates[peak_index])
    return selected, candidates[peak_index]


def select_cluster_count(
    rows: list[FeatureRow],
    matrix: np.ndarray,
    weights: dict[str, float],
    *,
    seed: int,
    reference_runs: int = REFERENCE_RUNS,
    granularity: int = 0,
    reference_samples: list[list[FeatureRow]] | None = None,
) -> ClusterSelection:
    count = len(rows)
    if count <= 2:
        return ClusterSelection(_cluster(matrix, 1), 1, 1, 1, (0.0,), (0.0,), 1)
    max_clusters = min(count - 1, ceil(sqrt(count)) + 1)
    candidates = list(range(1, max_clusters + 1))
    observed_labels = _cluster_candidates(matrix, candidates)
    observed = [_dispersion(matrix, observed_labels[value]) for value in candidates]
    reference_logs: list[list[float]] = [[] for _ in candidates]
    samples = reference_samples or _reference_samples(rows, seed=seed, sample_count=max(2, reference_runs))
    for reference_rows in samples:
        reference_matrix, _ = distance_matrix(reference_rows, weights)
        reference_labels = _cluster_candidates(reference_matrix, candidates)
        for index, value in enumerate(candidates):
            reference_logs[index].append(float(np.log(_dispersion(reference_matrix, reference_labels[value]))))
    gaps = [float(np.mean(values) - np.log(observed[index])) for index, values in enumerate(reference_logs)]
    errors = [float(np.std(values, ddof=1) * sqrt(1.0 + 1.0 / len(values))) for values in reference_logs]
    auto_selected, peak = _select_from_gap(gaps, errors, candidates)
    selected = int(np.clip(auto_selected + granularity, 1, max_clusters))
    return ClusterSelection(
        labels=observed_labels[selected],
        auto_selected_k=auto_selected,
        selected_k=selected,
        peak_k=peak,
        gaps=tuple(round(value, 6) for value in gaps),
        standard_errors=tuple(round(value, 6) for value in errors),
        max_clusters=max_clusters,
    )


def _boundary_positions(labels: np.ndarray) -> set[int]:
    return {index for index in range(len(labels) - 1) if labels[index] != labels[index + 1]}


def clustering_stability(
    rows: list[FeatureRow],
    base_selection: ClusterSelection,
    weights: dict[str, float],
    *,
    granularity: int,
    seed: int,
    runs: int = STABILITY_RUNS,
    reference_runs: int = REFERENCE_RUNS,
    reference_samples: list[list[FeatureRow]] | None = None,
) -> StabilityResult:
    if len(rows) <= 1:
        return StabilityResult((), 1.0, (1,))
    rng = np.random.default_rng(seed)
    counts = np.zeros(len(rows) - 1, dtype=np.float64)
    channels = list(weights)
    auto_values: list[int] = []
    shared_reference_samples = reference_samples or _reference_samples(
        rows, seed=seed ^ 0x51A81E, sample_count=max(4, reference_runs // 2)
    )
    for run_index in range(max(1, runs)):
        factors = rng.lognormal(mean=0.0, sigma=0.10, size=len(channels))
        perturbed = {channel: weights[channel] * float(factors[index]) for index, channel in enumerate(channels)}
        total = sum(perturbed.values())
        perturbed = {channel: value / total for channel, value in perturbed.items()}
        matrix, _ = distance_matrix(rows, perturbed)
        selection = select_cluster_count(
            rows,
            matrix,
            perturbed,
            seed=seed ^ ((run_index + 1) * 0x9E3779B1),
            reference_runs=max(4, reference_runs // 2),
            granularity=granularity,
            reference_samples=shared_reference_samples,
        )
        auto_values.append(selection.auto_selected_k)
        for boundary in _boundary_positions(selection.labels):
            counts[boundary] += 1
    return StabilityResult(
        boundaries=tuple(round(float(value / max(1, runs)), 4) for value in counts),
        k_selection_stability=round(sum(value == base_selection.auto_selected_k for value in auto_values) / len(auto_values), 4),
        auto_k_values=tuple(auto_values),
    )


def _cluster_indices(labels: np.ndarray) -> list[list[int]]:
    groups: list[list[int]] = []
    for index, label in enumerate(labels):
        while len(groups) <= int(label):
            groups.append([])
        groups[int(label)].append(index)
    return [group for group in groups if group]


def _quality_scores(
    matrix: np.ndarray,
    labels: np.ndarray,
    boundary_scores: tuple[float, ...],
    k_selection_stability: float,
) -> dict[int, float]:
    count = len(labels)
    unique = sorted(set(int(value) for value in labels))
    if 1 < len(unique) < count:
        silhouettes = (silhouette_samples(matrix, labels, metric="precomputed") + 1.0) / 2.0
    else:
        cohesion = 1.0 - float(matrix[np.triu_indices(count, 1)].mean()) if count > 1 else 1.0
        silhouettes = np.full(count, np.clip(cohesion, 0.0, 1.0))
    scores: dict[int, float] = {}
    for group in _cluster_indices(labels):
        left, right = group[0], group[-1]
        stability_terms = []
        if left > 0:
            stability_terms.append(boundary_scores[left - 1])
        if right < count - 1:
            stability_terms.append(boundary_scores[right])
        stability_terms.extend(1.0 - boundary_scores[index] for index in range(left, right))
        boundary_stability = float(np.mean(stability_terms)) if stability_terms else 1.0
        silhouette = float(np.mean(silhouettes[group]))
        scores[int(labels[group[0]])] = round(float(np.clip(
            0.45 * boundary_stability + 0.35 * silhouette + 0.20 * k_selection_stability,
            0.0,
            1.0,
        )), 4)
    return scores


def _seed_for(rows: list[FeatureRow], suffix: str) -> int:
    payload = "|".join(str(row.photo.get("id") or row.original_index) for row in rows) + suffix
    return int.from_bytes(sha256(payload.encode()).digest()[:8], "big", signed=False)


def _weighted_coverage(coverage: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(weights[channel] * coverage.get(channel, 0.0) for channel in weights), 4)


def _ordered_rows(photos: list[dict[str, Any]]) -> tuple[list[FeatureRow], list[FeatureRow]]:
    rows = [_feature_row(photo, index) for index, photo in enumerate(photos)]
    dimensions = Counter(row.embedding.shape for row in rows if row.embedding is not None)
    if dimensions:
        expected_shape = dimensions.most_common(1)[0][0]
        rows = [
            row if row.embedding is None or row.embedding.shape == expected_shape else replace(row, embedding=None)
            for row in rows
        ]
    timed = sorted((row for row in rows if row.taken_at is not None), key=lambda row: (row.taken_at, str(row.photo.get("id") or "")))
    untimed = sorted((row for row in rows if row.taken_at is None), key=lambda row: (row.original_index, str(row.photo.get("id") or "")))
    return timed, untimed


def _assign_untimed(groups: list[list[FeatureRow]], untimed: list[FeatureRow], weights: dict[str, float]) -> set[int]:
    degraded_groups: set[int] = set()
    for row in untimed:
        if not groups:
            groups.append([row])
            degraded_groups.add(0)
            continue
        scores = []
        for group in groups:
            distances = [float(distance_matrix([row, member], weights, include_time=False)[0][0, 1]) for member in group]
            scores.append(float(np.mean(distances)) if distances else 1.0)
        target = int(np.argmin(scores))
        groups[target].append(row)
        degraded_groups.add(target)
    return degraded_groups


def _segment_payloads(
    rows: list[FeatureRow],
    parent_seed: int,
    *,
    reference_runs: int,
    stability_runs: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: (row.taken_at or datetime.max, row.original_index, str(row.photo.get("id") or "")))
    matrix, coverage = distance_matrix(ordered, SEGMENT_WEIGHTS)
    segment_reference_runs = min(reference_runs, 5)
    segment_stability_runs = min(stability_runs, 5)
    reference_samples = _reference_samples(
        ordered,
        seed=parent_seed,
        sample_count=max(2, segment_reference_runs),
    )
    selection = select_cluster_count(
        ordered,
        matrix,
        SEGMENT_WEIGHTS,
        seed=parent_seed,
        reference_runs=segment_reference_runs,
        reference_samples=reference_samples,
    )
    stability = clustering_stability(
        ordered,
        selection,
        SEGMENT_WEIGHTS,
        granularity=0,
        seed=parent_seed ^ 0x5E6D3,
        runs=segment_stability_runs,
        reference_runs=segment_reference_runs,
        reference_samples=reference_samples,
    )
    qualities = _quality_scores(matrix, selection.labels, stability.boundaries, stability.k_selection_stability)
    segments = []
    for index, group in enumerate(_cluster_indices(selection.labels)):
        members = [ordered[item] for item in group]
        label = int(selection.labels[group[0]])
        quality = qualities[label]
        segments.append({
            "segment_key": f"segment-{index + 1}",
            "name": f"活动阶段 {index + 1}",
            "description": "",
            "segment_type": "embedding",
            "time_range": time_range_label([member.photo for member in members]),
            "photo_ids": [str(member.photo["id"]) for member in members],
            "clustering_quality": quality,
            "clustering_needs_review": quality < QUALITY_REVIEW_THRESHOLD or stability.k_selection_stability < K_STABILITY_REVIEW_THRESHOLD,
            "clustering_explanation": {
                "quality_score": quality,
                "boundary_stability": stability.boundaries,
                "feature_coverage": coverage,
                "auto_selected_k": selection.auto_selected_k,
                "selected_k": selection.selected_k,
                "peak_k": selection.peak_k,
                "k_selection_stability": stability.k_selection_stability,
                "selection_method": "gap_global_one_standard_error",
                "partition_method": "sequential_dynamic_programming",
            },
        })
    return segments, {
        "auto_selected_k": selection.auto_selected_k,
        "selected_k": selection.selected_k,
        "peak_k": selection.peak_k,
        "k_selection_stability": stability.k_selection_stability,
        "gaps": selection.gaps,
        "standard_errors": selection.standard_errors,
    }


def cluster_sequential_photos(
    photos: list[dict[str, Any]],
    *,
    strategy: str = "balanced",
    granularity: int = 0,
    reference_runs: int = REFERENCE_RUNS,
    stability_runs: int = STABILITY_RUNS,
) -> list[dict[str, Any]]:
    if not photos:
        return []
    resolved_strategy = strategy if strategy in STRATEGY_WEIGHTS else "balanced"
    weights = dict(STRATEGY_WEIGHTS[resolved_strategy])
    granularity = int(np.clip(granularity, -2, 2))
    timed, untimed = _ordered_rows(photos)
    clustering_rows = timed or untimed
    matrix, coverage = distance_matrix(clustering_rows, weights)
    seed = _seed_for(clustering_rows, f"{resolved_strategy}:{granularity}")
    reference_samples = _reference_samples(
        clustering_rows,
        seed=seed,
        sample_count=max(2, reference_runs),
    )
    selection = select_cluster_count(
        clustering_rows,
        matrix,
        weights,
        seed=seed,
        reference_runs=reference_runs,
        granularity=granularity,
        reference_samples=reference_samples,
    )
    stability = clustering_stability(
        clustering_rows,
        selection,
        weights,
        granularity=granularity,
        seed=seed ^ 0xC7C7,
        runs=stability_runs,
        reference_runs=reference_runs,
        reference_samples=reference_samples,
    )
    qualities = _quality_scores(matrix, selection.labels, stability.boundaries, stability.k_selection_stability)
    label_groups = _cluster_indices(selection.labels)
    groups = [[clustering_rows[item] for item in group] for group in label_groups]
    degraded_groups = _assign_untimed(groups, untimed if timed else [], weights)
    weighted_coverage = _weighted_coverage(coverage, weights)
    chapters: list[dict[str, Any]] = []
    for index, rows in enumerate(groups):
        base_label = int(selection.labels[label_groups[index][0]])
        quality = round(qualities[base_label] * (0.85 if index in degraded_groups else 1.0), 4)
        segment_seed = seed ^ int.from_bytes(sha256(str(index).encode()).digest()[:8], "big")
        segments, segment_selection = _segment_payloads(
            rows,
            segment_seed,
            reference_runs=reference_runs,
            stability_runs=stability_runs,
        )
        ordered_members = sorted(rows, key=lambda row: (row.taken_at or datetime.max, row.original_index, str(row.photo.get("id") or "")))
        representative_ids = select_representative_photos([row.photo for row in ordered_members])
        left, right = label_groups[index][0], label_groups[index][-1]
        boundary_scores = {
            "left": stability.boundaries[left - 1] if left > 0 else 1.0,
            "right": stability.boundaries[right] if right < len(clustering_rows) - 1 else 1.0,
        }
        needs_review = (
            quality < QUALITY_REVIEW_THRESHOLD
            or weighted_coverage < COVERAGE_REVIEW_THRESHOLD
            or stability.k_selection_stability < K_STABILITY_REVIEW_THRESHOLD
            or index in degraded_groups
        )
        chapters.append({
            "chapter_key": f"chapter-{index + 1}",
            "name": f"第 {index + 1} 章",
            "description": "",
            "time_range": time_range_label([row.photo for row in ordered_members]),
            "photo_ids": [str(row.photo["id"]) for row in ordered_members],
            "segments": segments,
            "clustering_source": "algorithm",
            "clustering_algorithm_version": ALGORITHM_VERSION,
            "clustering_quality": quality,
            "clustering_needs_review": needs_review,
            "clustering_explanation": {
                "quality_score": quality,
                "strategy": resolved_strategy,
                "weights": weights,
                "auto_selected_k": selection.auto_selected_k,
                "selected_k": selection.selected_k,
                "peak_k": selection.peak_k,
                "granularity": granularity,
                "k_selection_stability": stability.k_selection_stability,
                "k_selection_values": stability.auto_k_values,
                "selection_method": "gap_global_one_standard_error",
                "partition_method": "sequential_dynamic_programming",
                "gap_values": selection.gaps,
                "gap_standard_errors": selection.standard_errors,
                "boundary_stability": boundary_scores,
                "all_boundary_stability": stability.boundaries,
                "feature_coverage": coverage,
                "weighted_feature_coverage": weighted_coverage,
                "degraded_photo_count": sum(row.taken_at is None or row.embedding is None for row in rows),
                "representative_photo_ids": representative_ids,
                "segment_selection": segment_selection,
            },
        })
    return chapters


__all__ = [
    "ALGORITHM_VERSION",
    "SEGMENT_WEIGHTS",
    "STRATEGY_WEIGHTS",
    "cluster_sequential_photos",
    "distance_matrix",
    "select_cluster_count",
]
