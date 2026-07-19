from __future__ import annotations

import inspect
from datetime import datetime, timedelta
from math import ceil, sqrt

from app.ai.dashscope_multimodal_embedding_provider import (
    DashScopeMultimodalEmbeddingProvider,
    EmbeddingProviderError,
)
from app.engines.chapter_engine import sequential_clusterer
from app.engines.chapter_engine.features import scene_similarity
from app.engines.chapter_engine.sequential_clusterer import (
    ALGORITHM_VERSION,
    STRATEGY_WEIGHTS,
    cluster_sequential_photos,
)
from app.engines.chapter_engine.service import cluster_photos
from app.services.chapter_feature_service import ChapterFeatureService
from scripts.evaluate_chapter_clustering import evaluate


def _photo(
    photo_id: str,
    taken_at: str | None,
    embedding: list[float] | None,
) -> dict:
    histogram = [0.0] * 48
    histogram[0] = 1.0
    return {
        "id": photo_id,
        "filename": f"{photo_id}.jpg",
        "taken_at": taken_at,
        "gps_latitude": 30.0,
        "gps_longitude": 120.0,
        "cleaning_features": {"color_histogram": histogram},
        "chapter_features": {
            "embedding": embedding or [],
            "embedding_model": "qwen3-vl-embedding",
        },
    }


def _activity_sequence(group_count: int = 6, photos_per_group: int = 4) -> list[dict]:
    started = datetime(2026, 7, 17, 10, 0)
    photos = []
    dimensions = max(group_count + 2, 8)
    for group in range(group_count):
        for offset in range(photos_per_group):
            visual = [0.0] * dimensions
            visual[group] = 1.0
            visual[-1] = 0.02 * offset
            photos.append(_photo(
                f"g{group}-{offset}",
                (started + timedelta(minutes=len(photos) * 3)).isoformat(),
                visual,
            ))
    return photos


def _cluster(photos: list[dict], strategy: str = "balanced") -> list[dict]:
    return cluster_sequential_photos(
        photos,
        strategy=strategy,
        reference_runs=4,
        stability_runs=4,
    )


def test_gap_statistic_finds_contiguous_activity_groups_without_hard_boundaries():
    chapters = _cluster(_activity_sequence(), "activity_first")
    assert len(chapters) == 6
    assert [len(chapter["photo_ids"]) for chapter in chapters] == [4] * 6
    assert all(chapter["clustering_algorithm_version"] == ALGORITHM_VERSION for chapter in chapters)
    assert all(chapter["clustering_explanation"]["selection_method"] == "gap_global_one_standard_error" for chapter in chapters)
    assert all(chapter["clustering_explanation"]["partition_method"] == "sequential_dynamic_programming" for chapter in chapters)
    assert [chapter["chapter_key"] for chapter in chapters] == [f"chapter-{index}" for index in range(1, 7)]


def test_same_activity_with_visual_variation_stays_in_one_chapter_and_can_have_segments():
    photos = _activity_sequence(group_count=1, photos_per_group=8)
    for index, photo in enumerate(photos):
        photo["chapter_features"]["embedding"] = [1.0, index / 20, 0.0, 0.0]
    chapters = _cluster(photos, "activity_first")
    assert len(chapters) == 1
    assert chapters[0]["photo_ids"] == [photo["id"] for photo in photos]
    assert chapters[0]["segments"]


def test_clustering_is_deterministic_and_each_chapter_is_a_contiguous_interval():
    photos = _activity_sequence(group_count=4, photos_per_group=3)
    first = _cluster(photos)
    second = _cluster(list(reversed(photos)))
    assert first == second
    ordered_ids = [photo["id"] for photo in photos]
    positions = {photo_id: index for index, photo_id in enumerate(ordered_ids)}
    for chapter in first:
        chapter_positions = [positions[photo_id] for photo_id in chapter["photo_ids"]]
        assert chapter_positions == list(range(min(chapter_positions), max(chapter_positions) + 1))


def test_activity_strategy_is_only_a_soft_weight_profile():
    assert STRATEGY_WEIGHTS["activity_first"]["embedding"] > STRATEGY_WEIGHTS["balanced"]["embedding"]
    assert set(STRATEGY_WEIGHTS["balanced"]) == {"embedding", "time", "gps", "color"}
    source = inspect.getsource(sequential_clusterer)
    for forbidden in ("activity_change", "theme_activity_change", "SHORT_GAP", "SESSION_GAP", "LOCATION_SPLIT"):
        assert forbidden not in source


def test_untimed_and_partial_features_are_kept_but_lower_quality():
    photos = _activity_sequence(group_count=2, photos_per_group=3)
    photos.append(_photo("untimed", None, [1.0, 0.0, 0.0]))
    photos[1]["chapter_features"]["embedding"] = []
    chapters = _cluster(photos)
    assigned = [photo_id for chapter in chapters for photo_id in chapter["photo_ids"]]
    assert sorted(assigned) == sorted(photo["id"] for photo in photos)
    untimed_chapter = next(chapter for chapter in chapters if "untimed" in chapter["photo_ids"])
    assert untimed_chapter["clustering_explanation"]["degraded_photo_count"] > 0
    assert untimed_chapter["clustering_needs_review"] is True


def test_no_embedding_uses_explicit_c1_fallback_and_never_reports_quality():
    chapters = cluster_photos([
        _photo("a", "2026-07-17T10:00:00", None),
        _photo("b", "2026-07-17T11:00:00", None),
    ])
    assert chapters[0]["clustering_algorithm_version"] == "c1-events-v1"
    assert chapters[0]["clustering_quality"] is None
    assert chapters[0]["clustering_needs_review"] is True


def test_technical_scene_tags_are_not_semantic_evidence():
    assert scene_similarity(
        {"scene_tags": ["high_resolution", "png_format"]},
        {"scene_tags": ["high_resolution", "png_format"]},
    ) is None


def test_global_one_standard_error_does_not_stop_at_early_local_plateau():
    gaps = [0.048008, 0.238308, 0.237247, 0.235557, 0.239841, 0.247629, 0.425432, 0.429062, 0.442494]
    errors = [0.002749, 0.016633, 0.018207, 0.020051, 0.022027, 0.019522, 0.019944, 0.021179, 0.019421]
    selected, peak = sequential_clusterer._select_from_gap(gaps, errors, list(range(1, 10)))
    assert peak == 9
    assert selected == 7


def test_granularity_offsets_only_the_auto_selected_chapter_count():
    photos = _activity_sequence(group_count=6, photos_per_group=4)
    automatic = cluster_sequential_photos(photos, reference_runs=4, stability_runs=2)
    coarse = cluster_sequential_photos(photos, granularity=-2, reference_runs=4, stability_runs=2)
    detailed = cluster_sequential_photos(photos, granularity=2, reference_runs=4, stability_runs=2)
    auto_k = automatic[0]["clustering_explanation"]["auto_selected_k"]
    max_k = min(len(photos) - 1, ceil(sqrt(len(photos))) + 1)
    assert len(automatic) == auto_k
    assert len(coarse) == max(1, auto_k - 2)
    assert len(detailed) == min(max_k, auto_k + 2)
    assert automatic[0]["clustering_explanation"]["granularity"] == 0
    assert all(segment["segment_key"].startswith("segment-") for chapter in automatic for segment in chapter["segments"])


def test_chapter_feature_extraction_has_no_per_photo_llm_path():
    source = inspect.getsource(ChapterFeatureService)
    assert "infer_json" not in source
    assert "semantic" not in source


def test_dashscope_response_validation_normalizes_and_checks_dimension():
    vectors = DashScopeMultimodalEmbeddingProvider._extract_embeddings(
        {"output": {"embeddings": [{"index": 0, "embedding": [3.0, 4.0]}]}},
        expected=1,
        dimension=2,
    )
    assert vectors == [[0.6, 0.8]]
    try:
        DashScopeMultimodalEmbeddingProvider._extract_embeddings(
            {"output": {"embeddings": [{"index": 0, "embedding": [1.0]}]}},
            expected=1,
            dimension=2,
        )
    except EmbeddingProviderError as exc:
        assert "dimension" in str(exc)
    else:
        raise AssertionError("dimension mismatch should fail")


def test_chapter_evaluator_reports_boundary_and_cluster_metrics():
    result = evaluate([
        {"photo_id": "a", "expected_chapter": "one", "predicted_chapter": "one"},
        {"photo_id": "b", "expected_chapter": "one", "predicted_chapter": "one"},
        {"photo_id": "c", "expected_chapter": "two", "predicted_chapter": "two"},
    ])
    assert result["boundary_f1"] == 1.0
    assert result["adjusted_rand_index"] == 1.0
    assert result["oversegmentation_ratio"] == 1.0
