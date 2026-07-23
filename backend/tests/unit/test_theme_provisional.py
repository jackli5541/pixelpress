from __future__ import annotations

import math
from datetime import UTC, datetime

from app.engines.theme_pipeline import fill_theme_candidates
from app.engines.theme_relevance_engine import RelevanceCalibration, ThemeQuery, score_photo_relevance


def _missing_calibration() -> RelevanceCalibration:
    return RelevanceCalibration.from_dict({}, load_status="missing")


def _query() -> ThemeQuery:
    return ThemeQuery(
        positive_vector=[1.0, 0.0],
        provider="test-provider",
        model="test-model",
        dimension=2,
    )


def _score(rank_score: float, *, taken_at=None, constraints=None):  # noqa: ANN001
    signal = rank_score * 2.0 - 1.0
    vector = [signal, math.sqrt(1.0 - signal * signal)]
    return score_photo_relevance(
        photo_id="photo",
        photo_vector=vector,
        photo_provider="test-provider",
        photo_model="test-model",
        photo_dimension=2,
        taken_at=taken_at,
        query=_query(),
        calibration=_missing_calibration(),
        provisional_auto_decision_enabled=True,
        provisional_decision_threshold=0.60,
        constraints=constraints or {},
        feature_version="test-features",
    )


def test_provisional_threshold_is_inclusive():
    keep = _score(0.6000)
    exclude = _score(0.5999)

    assert keep["suggested_decision"] == "keep"
    assert keep["relevance_label"] == "relevant"
    assert keep["evidence_json"]["decision_mode"] == "provisional_binary"
    assert keep["evidence_json"]["provisional_threshold"] == 0.60
    assert exclude["suggested_decision"] == "exclude"
    assert exclude["relevance_label"] == "off_theme"


def test_provisional_time_constraints_keep_technical_review():
    constraints = {"time": {"years": [2026]}}
    missing_time = _score(0.9, constraints=constraints)
    outside_time = _score(
        0.9,
        constraints=constraints,
        taken_at=datetime(2025, 12, 31, tzinfo=UTC),
    )

    assert missing_time["suggested_decision"] == "review"
    assert "missing_capture_time" in missing_time["reasons_json"]
    assert outside_time["suggested_decision"] == "exclude"
    assert "outside_requested_year" in outside_time["reasons_json"]


def test_fallback_candidates_are_deterministic():
    normal, preset_count = fill_theme_candidates([], candidate_count=3)
    custom, custom_preset_count = fill_theme_candidates(
        [],
        candidate_count=3,
        custom_theme="我的夏日散步",
    )

    assert [item["title"] for item in normal] == ["旅行见闻", "亲友相聚", "日常片段"]
    assert [item["id"] for item in normal] == [
        "preset-travel-notes",
        "preset-family-gathering",
        "preset-daily-moments",
    ]
    assert preset_count == 3
    assert [item["title"] for item in custom] == ["我的夏日散步", "旅行见闻", "亲友相聚"]
    assert custom[0]["source"] == "custom"
    assert custom_preset_count == 2


def test_partial_candidates_are_filled_without_duplicate_titles():
    candidates, preset_count = fill_theme_candidates(
        [{
            "id": "candidate-1",
            "title": "旅行见闻",
            "constraints": {},
            "recommended_strategy": "balanced",
            "source": "ai",
        }],
        candidate_count=3,
    )

    assert [item["title"] for item in candidates] == ["旅行见闻", "亲友相聚", "日常片段"]
    assert preset_count == 2
