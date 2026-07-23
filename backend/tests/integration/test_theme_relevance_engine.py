from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.ai.dashscope_multimodal_embedding_provider import DashScopeMultimodalEmbeddingProvider
from app.ai.types import ProviderConnectionConfig, TextEmbeddingRequest
from app.engines.theme_relevance_engine import (
    QUERY_VERSION,
    SCORING_VERSION,
    RelevanceCalibration,
    ThemeQuery,
    build_query_texts,
    query_similarity_features,
    score_photo_relevance,
)
from scripts.evaluate_theme_relevance import evaluate


def _calibration(
    *,
    enabled: bool = True,
    provider: str = "test-provider",
    scoring_version: str = SCORING_VERSION,
) -> RelevanceCalibration:
    return RelevanceCalibration.from_dict({
        "version": "test-calibration-v1",
        "provider": provider,
        "model": "test-model",
        "dimension": 2,
        "query_version": QUERY_VERSION,
        "scoring_version": scoring_version,
        "enabled": enabled,
        "mapping": {"signal": [-1.0, 0.0, 1.0], "probability": [0.0, 0.5, 1.0]},
        "decision_thresholds": {"exclude_max_probability": 0.25, "keep_min_probability": 0.75},
        "metrics": {"candidate_precision": 0.95, "relevant_recall": 0.80, "false_exclusion_rate": 0.01},
        "requirements": {"requirements_met": True},
        "gates": {"candidate_precision": 0.90, "relevant_recall": 0.70, "false_exclusion_rate": 0.02},
    })


def _query(vector: list[float], negative: list[float] | None = None) -> ThemeQuery:
    return ThemeQuery(
        positive_vector=vector,
        provider="test-provider",
        model="test-model",
        dimension=2,
        negative_vectors=(negative,) if negative else (),
    )


def _score(
    vector,
    query,
    *,
    calibration=None,
    model="test-model",
    dimension=2,
    constraints=None,
    taken_at=None,
    provisional_enabled=False,
    provisional_threshold=0.60,
):  # noqa: ANN001
    return score_photo_relevance(
        photo_id="photo",
        photo_vector=vector,
        photo_provider="test-provider",
        photo_model=model,
        photo_dimension=dimension,
        taken_at=taken_at,
        query=query,
        calibration=calibration or _calibration(),
        provisional_auto_decision_enabled=provisional_enabled,
        provisional_decision_threshold=provisional_threshold,
        constraints=constraints or {},
        feature_version="features-v1",
    )


def test_cross_modal_engine_is_theme_agnostic_and_never_forces_top_k():
    for query_vector, relevant, unrelated in (
        ([1.0, 0.0], [1.0, 0.0], [-1.0, 0.0]),
        ([0.0, 1.0], [0.0, 1.0], [0.0, -1.0]),
        ([-1.0, 0.0], [-1.0, 0.0], [1.0, 0.0]),
    ):
        query = _query(query_vector)
        assert _score(relevant, query)["suggested_decision"] == "keep"
        assert _score(unrelated, query)["suggested_decision"] == "exclude"
        assert _score([0.0, 1.0] if query_vector[0] else [1.0, 0.0], query)["suggested_decision"] == "review"


def test_generic_semantic_tags_cannot_create_a_fake_high_score():
    class PhotoStub:
        id = "outdoor-shopping"
        taken_at = None

    feature = {
        "embedding": [0.0, 1.0],
        "embedding_model": "test-model",
        "embedding_dimension": 2,
        "feature_version": "features-v1",
        "setting": "outdoor",
        "activities": ["shopping", "walking"],
        "scenes": ["park"],
    }
    payload = score_photo_relevance(
        photo_id=PhotoStub.id,
        photo_vector=feature["embedding"],
        photo_provider="test-provider",
        photo_model=feature["embedding_model"],
        photo_dimension=feature["embedding_dimension"],
        taken_at=None,
        query=_query([1.0, 0.0]),
        calibration=_calibration(),
        constraints={},
        feature_version=feature["feature_version"],
    )
    assert payload["relevance_score"] == 0.5
    assert payload["suggested_decision"] == "review"
    assert "matched_theme_concept" not in payload["reasons_json"]


def test_negative_query_penalizes_only_when_it_matches_more_strongly():
    query = _query([0.8, 0.2], negative=[1.0, 0.0])
    result = _score([1.0, 0.0], query)
    assert result["evidence_json"]["negative_similarity"] > result["evidence_json"]["positive_similarity"]
    assert result["evidence_json"]["signal"] < result["evidence_json"]["positive_similarity"]


def test_missing_calibration_or_embedding_mismatch_requires_review():
    query = _query([1.0, 0.0])
    assert _score([1.0, 0.0], query, calibration=_calibration(enabled=False))["suggested_decision"] == "review"
    mismatch = _score([1.0, 0.0], query, model="other-model")
    assert mismatch["suggested_decision"] == "review"
    assert "embedding_model_mismatch" in mismatch["reasons_json"]
    provider_mismatch = _score(
        [1.0, 0.0],
        query,
        calibration=_calibration(provider="other-provider"),
    )
    assert provider_mismatch["suggested_decision"] == "review"
    assert provider_mismatch["evidence_json"]["calibration_status"] == "mismatch"
    scoring_mismatch = _score(
        [1.0, 0.0],
        query,
        calibration=_calibration(scoring_version="old-scoring"),
    )
    assert scoring_mismatch["suggested_decision"] == "review"


def test_uncalibrated_scoring_keeps_raw_features_without_album_percentiles():
    result = _score([1.0, 0.0], _query([1.0, 0.0]), calibration=_calibration(enabled=False))
    assert result["suggested_decision"] == "review"
    assert result["evidence_json"]["raw_query_similarity"] == 1.0
    assert result["evidence_json"]["score_kind"] == "embedding_similarity_rank"
    assert result["evidence_json"]["calibration_status"] == "disabled"


def test_provisional_binary_threshold_is_inclusive_and_records_evidence():
    query = _query([1.0, 0.0])
    keep = _score(
        [0.2, 0.9797958971],
        query,
        calibration=_calibration(enabled=False),
        provisional_enabled=True,
    )
    exclude = _score(
        [0.1998, 0.9798367],
        query,
        calibration=_calibration(enabled=False),
        provisional_enabled=True,
    )
    missing_calibration = RelevanceCalibration.from_dict({}, load_status="missing")
    missing = _score(
        [0.2, 0.9797958971],
        query,
        calibration=missing_calibration,
        provisional_enabled=True,
    )

    assert keep["relevance_score"] == 0.6
    assert keep["suggested_decision"] == "keep"
    assert keep["relevance_label"] == "relevant"
    assert keep["evidence_json"]["decision_mode"] == "provisional_binary"
    assert keep["evidence_json"]["provisional_threshold"] == 0.6
    assert exclude["relevance_score"] == 0.5999
    assert exclude["suggested_decision"] == "exclude"
    assert exclude["relevance_label"] == "off_theme"
    assert missing["suggested_decision"] == "keep"
    assert missing["evidence_json"]["calibration_status"] == "missing"


def test_calibrated_and_technical_review_paths_override_provisional_decisions():
    query = _query([1.0, 0.0])
    calibrated = _score(
        [0.6, 0.8],
        query,
        provisional_enabled=True,
        provisional_threshold=0.95,
    )
    mismatch = _score(
        [1.0, 0.0],
        query,
        calibration=_calibration(enabled=False),
        model="other-model",
        provisional_enabled=True,
    )
    invalid = _score(
        [0.0, 0.0],
        query,
        calibration=_calibration(enabled=False),
        provisional_enabled=True,
    )
    calibration_mismatch = _score(
        [1.0, 0.0],
        query,
        calibration=_calibration(provider="other-provider"),
        provisional_enabled=True,
    )

    assert calibrated["suggested_decision"] == "keep"
    assert calibrated["evidence_json"]["decision_mode"] == "calibrated"
    assert calibrated["evidence_json"]["provisional_threshold"] is None
    assert mismatch["suggested_decision"] == "review"
    assert invalid["suggested_decision"] == "review"
    assert calibration_mismatch["suggested_decision"] == "review"
    assert calibration_mismatch["evidence_json"]["decision_mode"] == "manual_review"


def test_provisional_time_constraints_review_missing_time_and_exclude_mismatch():
    query = _query([1.0, 0.0])
    common = {
        "calibration": _calibration(enabled=False),
        "constraints": {"time": {"years": [2026]}},
        "provisional_enabled": True,
    }
    missing = _score([1.0, 0.0], query, **common)
    outside = _score(
        [1.0, 0.0],
        query,
        taken_at=datetime(2025, 12, 31, tzinfo=UTC),
        **common,
    )

    assert missing["suggested_decision"] == "review"
    assert "missing_capture_time" in missing["reasons_json"]
    assert outside["suggested_decision"] == "exclude"
    assert "outside_requested_year" in outside["reasons_json"]


def test_query_features_keep_raw_expansion_and_negative_scores_separate():
    query = ThemeQuery(
        positive_vector=[1.0, 0.0],
        provider="test-provider",
        model="test-model",
        dimension=2,
        expansion_vectors=([0.8, 0.2],),
        negative_vectors=([0.0, 1.0],),
    )
    features = query_similarity_features([1.0, 0.0], query)
    assert features["raw_query_similarity"] == 1.0
    assert features["expanded_query_similarity"] < features["raw_query_similarity"]
    assert features["margin"] > 0


def test_explicit_time_constraints_remain_deterministic():
    result = _score(
        [1.0, 0.0],
        _query([1.0, 0.0]),
        constraints={"time": {"years": [2026]}},
        taken_at=datetime(2025, 12, 31, tzinfo=UTC),
    )
    assert result["suggested_decision"] == "exclude"
    assert result["relevance_score"] == 0.0
    uncalibrated = _score(
        [1.0, 0.0],
        _query([1.0, 0.0]),
        calibration=_calibration(enabled=False),
        constraints={"time": {"years": [2026]}},
        taken_at=datetime(2025, 12, 31, tzinfo=UTC),
    )
    assert uncalibrated["suggested_decision"] == "review"
    assert "constraint_mismatch_unconfirmed" in uncalibrated["reasons_json"]


def test_query_builder_preserves_raw_theme_and_separates_exclusions():
    texts, negative = build_query_texts({
        "title": "任意主题",
        "constraints": {
            "activities": ["activity-a"],
            "people": ["group"],
            "include_concepts": ["concept-a"],
            "exclude_concepts": ["concept-b"],
        },
        "_query_spec": {
            "entailed_concepts": ["concept-a"],
            "negative_concepts": ["concept-b", "activity-a", "group"],
        },
    }, custom_input="用户原始主题")
    assert texts[0] == "用户原始主题"
    assert "concept-a" in texts[1]
    assert "activity-a" not in texts[1]
    assert "group" not in texts[1]
    assert "concept-b" not in texts[1]
    assert "concept-b" in negative


def test_text_embedding_provider_uses_text_contents_and_normalizes(monkeypatch):
    provider = DashScopeMultimodalEmbeddingProvider()
    captured = {}

    async def fake_embed(contents, *, model, dimension, connection):  # noqa: ANN001
        captured["contents"] = contents
        return [[1.0, 0.0], [0.0, 1.0]], {
            "model": model,
            "provider": provider.provider_name,
            "debug": {},
        }

    monkeypatch.setattr(provider, "_embed_contents", fake_embed)
    response = asyncio.run(provider.embed_texts(TextEmbeddingRequest(
        texts=["主题一", "主题二"],
        model="test-model",
        dimension=2,
        connection=ProviderConnectionConfig(
            provider=provider.provider_name,
            api_key="test",
            api_url=None,
            model="test-model",
            source="test",
        ),
    )))
    assert captured["contents"] == [{"text": "主题一"}, {"text": "主题二"}]
    assert response.embeddings == [[1.0, 0.0], [0.0, 1.0]]


def test_calibration_report_enables_only_a_large_multi_theme_dataset():
    records = []
    for index in range(512):
        relevant = index % 2 == 0
        records.append({
            "album_id": f"album-{index % 25}",
            "photo_id": f"photo-{index}",
            "theme_id": f"theme-{index % 8}",
            "theme_category": f"category-{index % 8}",
            "label": "relevant" if relevant else "off_theme",
            "positive_similarity": 0.9 if relevant else -0.9,
            "negative_similarity": None,
            "provider": "dashscope_multimodal_embedding",
            "model": "qwen3-vl-embedding",
            "dimension": 512,
            "query_version": QUERY_VERSION,
            "scoring_version": SCORING_VERSION,
            "annotators": ["a", "b"],
        })
    report = evaluate(records, dataset_version="multi-theme-v1")
    assert report["enabled"] is True
    assert report["metrics"]["candidate_precision"] == 1.0
    assert report["metrics"]["false_exclusion_rate"] == 0.0

    assert evaluate(records[:100], dataset_version="too-small")["enabled"] is False
    single_annotator = [{**item, "annotators": ["a"]} for item in records]
    assert evaluate(single_annotator, dataset_version="single-annotator")["enabled"] is False
    mixed_provider = list(records)
    mixed_provider[0] = {**mixed_provider[0], "provider": "other-provider"}
    assert evaluate(mixed_provider, dataset_version="mixed-provider")["enabled"] is False
