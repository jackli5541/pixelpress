from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.ai.schemas import ThemeCandidateBatchOutput
from app.ai.types import ProviderConnectionConfig, ProviderResponse
from app.core.config import get_settings
from app.db import session as db_session
from app.engines.theme_pipeline import (
    build_theme_query_spec,
    generate_theme_candidates,
    normalize_theme_constraints,
    selected_theme_text,
)
from app.engines.theme_relevance_engine import (
    QUERY_VERSION,
    SCORING_VERSION,
    RelevanceCalibration,
    ThemeQuery,
    ThemeRelevanceEngine,
)
from app.models.photo import Photo
from app.services.chapter_feature_service import ChapterFeatureService
from app.services.theme_curation_service import ThemeCurationService
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


async def _set_capture_times(photo_ids: list[str]) -> None:
    async with db_session.AsyncSessionFactory() as session:
        result = await session.execute(select(Photo).where(Photo.id.in_(photo_ids)).order_by(Photo.filename))
        started = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
        for index, photo in enumerate(result.scalars().all()):
            photo.taken_at = started + timedelta(minutes=index * 5)
        await session.commit()


def _finish_cleaning(client, headers: dict[str, str], album_id: str, photo_ids: list[str]) -> None:
    queued = client.post(f"/api/v1/albums/{album_id}/clean", headers=headers)
    assert queued.status_code == 202
    run_task_worker(queued.json()["data"]["task"])
    response = client.patch(
        f"/api/v1/albums/{album_id}/clean/decisions",
        json={"photo_ids": photo_ids, "decision": "keep"},
        headers=headers,
    )
    assert response.status_code == 200


async def _fake_feature_extract(self, album_id, photos, *, progress_callback=None):  # noqa: ANN001
    del self, album_id
    features = {}
    for photo in photos:
        if "meal" in photo.filename:
            embedding = [1.0, 0.0]
        elif "game" in photo.filename:
            embedding = [0.0, 1.0]
        else:
            embedding = [-1.0, 0.0]
        features[photo.id] = {
            "embedding": embedding,
            "feature_status": "success",
            "feature_version": "test-theme-features-v1",
            "embedding_provider": "test-embedding-provider",
            "embedding_model": "test-embedding",
            "embedding_dimension": 2,
        }
    return features, {
        "embedding_success_count": len(photos),
        "embedding_failure_count": 0,
        "degraded_photo_count": 0,
    }


async def _fake_theme_candidates(feature_summary, *, images, candidate_count, provider_connection, custom_theme=None, excluded_titles=None):  # noqa: ANN001
    del feature_summary, images, candidate_count, provider_connection
    if excluded_titles:
        return [
            {
                "id": "candidate-2",
                "title": "亲友娱乐",
                "constraints": {"include_concepts": ["gaming"], "exclude_concepts": []},
                "recommended_strategy": "activity_first",
                "source": "ai",
            },
            {
                "id": "candidate-3",
                "title": "聚会合影",
                "constraints": {"include_concepts": ["group"], "exclude_concepts": []},
                "recommended_strategy": "balanced",
                "source": "ai",
            },
        ], {"provider": "fake", "model": "fake-theme-model"}
    return [{
        "id": "candidate-1",
        "title": custom_theme or "亲友聚会",
        "constraints": {
            "include_concepts": ["dining", "gaming", "group"],
            "exclude_concepts": ["screenshot", "document"],
        },
        "recommended_strategy": "activity_first",
        "source": "custom" if custom_theme else "ai",
    }], {"provider": "fake", "model": "fake-theme-model"}


async def _fake_theme_query(self, candidate, *, connection, dimension, custom_input=None):  # noqa: ANN001
    del self, candidate, connection, dimension, custom_input
    return ThemeQuery(
        positive_vector=[1.0, 0.0],
        provider="test-embedding-provider",
        model="test-embedding",
        dimension=2,
    )


async def _fake_query_spec(candidate, *, raw_theme, connection):  # noqa: ANN001
    del candidate, raw_theme, connection
    return {"entailed_concepts": [], "negative_concepts": []}


def _test_calibration() -> RelevanceCalibration:
    return RelevanceCalibration.from_dict({
        "version": "test-calibration-v1",
        "provider": "test-embedding-provider",
        "model": "test-embedding",
        "dimension": 2,
        "query_version": QUERY_VERSION,
        "scoring_version": SCORING_VERSION,
        "enabled": True,
        "mapping": {"signal": [-1.0, 0.0, 1.0], "probability": [0.0, 0.5, 1.0]},
        "decision_thresholds": {"exclude_max_probability": 0.25, "keep_min_probability": 0.75},
        "metrics": {"candidate_precision": 0.95, "relevant_recall": 0.80, "false_exclusion_rate": 0.01},
        "requirements": {"requirements_met": True},
        "gates": {"candidate_precision": 0.90, "relevant_recall": 0.70, "false_exclusion_rate": 0.02},
    })


def _enable_cross_modal_test_scoring(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(ThemeRelevanceEngine, "build_query", _fake_theme_query)
    monkeypatch.setattr("app.services.theme_curation_task_runner.build_theme_query_spec", _fake_query_spec)
    monkeypatch.setattr("app.services.theme_curation_task_runner.load_calibration", lambda path=None: _test_calibration())


def test_custom_theme_review_override_filters_photos_and_drives_chapter_strategy(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "theme_curation_enabled", True)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(ChapterFeatureService, "extract", _fake_feature_extract)
    monkeypatch.setattr("app.services.theme_curation_task_runner.generate_theme_candidates", _fake_theme_candidates)
    _enable_cross_modal_test_scoring(monkeypatch)

    headers = create_auth_headers(client, username="theme-owner", password="secret", role="user")
    album = create_album(client, headers, name="Theme Curation")
    meal = upload_photo(client, headers, album["id"], "meal.jpg")
    game = upload_photo(client, headers, album["id"], "game.jpg")
    document = upload_photo(client, headers, album["id"], "document.jpg")
    photo_ids = [meal["id"], game["id"], document["id"]]
    _finish_cleaning(client, headers, album["id"], photo_ids)
    asyncio.run(_set_capture_times(photo_ids))

    analysis = client.post(
        f"/api/v1/albums/{album['id']}/theme-analysis",
        json={"custom_theme": "亲友聚会"},
        headers=headers,
    )
    assert analysis.status_code == 202
    analysis_task = analysis.json()["data"]["task"]
    assert analysis_task["task_params"]["custom_theme"] == "亲友聚会"
    run_task_worker(analysis_task)

    workspace = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    assert workspace["phase"] == "choose_theme"
    assert len(workspace["profile"]["candidates"]) == 4
    custom_candidate = workspace["profile"]["candidates"][0]
    assert custom_candidate["source"] == "custom"
    assert custom_candidate["constraints"]["include_concepts"] == ["dining", "gaming", "group"]

    blocked = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["data"]["message"] == "theme review required"

    selection = client.post(
        f"/api/v1/albums/{album['id']}/theme-selection",
        json={
            "profile_id": workspace["profile"]["id"],
            "candidate_id": custom_candidate["id"],
            "chapter_strategy": "activity_first",
        },
        headers=headers,
    )
    assert selection.status_code == 202
    run_task_worker(selection.json()["data"]["task"])

    review = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    assessments = {item["photo"]["id"]: item for item in review["assessments"]}
    scores = [item["relevance_score"] for item in review["assessments"]]
    assert scores == sorted(scores, reverse=True)
    assert assessments[game["id"]]["suggested_decision"] == "review"
    assert assessments[document["id"]]["suggested_decision"] == "exclude"
    assert assessments[meal["id"]]["relevance_evidence"]["method"] == "cross_modal_embedding"

    restored = client.patch(
        f"/api/v1/albums/{album['id']}/theme-review/decisions",
        json={"photo_ids": [game["id"]], "decision": "keep"},
        headers=headers,
    )
    assert restored.status_code == 200
    confirmed = client.post(f"/api/v1/albums/{album['id']}/theme-review/confirm", headers=headers)
    assert confirmed.status_code == 200

    queued = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert queued.status_code == 202
    run_task_worker(queued.json()["data"]["task"])
    chapters = client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers).json()["data"]
    assigned = [photo_id for chapter in chapters for photo_id in chapter["photo_ids"]]
    assert meal["id"] in assigned
    assert game["id"] in assigned
    assert document["id"] not in assigned
    assert len(chapters) == 1
    assert all(chapter["clustering"]["algorithm_version"] == "c7-embedding-sequential-v1" for chapter in chapters)

    before_reopen = client.get(f"/api/v1/albums/{album['id']}", headers=headers).json()["data"]["content_revision"]
    reopened = client.post(
        f"/api/v1/albums/{album['id']}/theme-review/reopen",
        json={"confirm_rebuild": True},
        headers=headers,
    )
    assert reopened.status_code == 200
    after_reopen = client.get(f"/api/v1/albums/{album['id']}", headers=headers).json()["data"]["content_revision"]
    assert after_reopen == before_reopen + 1
    assert client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers).json()["data"] == []

    manual_chapter = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "temporary", "photo_ids": [meal["id"]]},
        headers=headers,
    ).json()["data"]
    review_workspace = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    before_selection = client.get(f"/api/v1/albums/{album['id']}", headers=headers).json()["data"]["content_revision"]
    rebuild_selection = client.post(
        f"/api/v1/albums/{album['id']}/theme-selection",
        json={
            "profile_id": review_workspace["profile"]["id"],
            "candidate_id": custom_candidate["id"],
            "chapter_strategy": "activity_first",
            "confirm_rebuild": True,
        },
        headers=headers,
    )
    assert rebuild_selection.status_code == 202
    run_task_worker(rebuild_selection.json()["data"]["task"])
    after_selection = client.get(f"/api/v1/albums/{album['id']}", headers=headers).json()["data"]["content_revision"]
    assert after_selection == before_selection + 1
    assert client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers).json()["data"] == []

    upload_photo(client, headers, album["id"], "new-photo.jpg")
    stale = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    assert stale["phase"] == "needs_analysis"


def test_theme_analysis_failure_falls_back_to_complete_record(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "theme_curation_enabled", True)
    monkeypatch.setattr(settings, "ai_enabled", False)

    headers = create_auth_headers(client, username="theme-fallback", password="secret", role="user")
    album = create_album(client, headers, name="Theme Fallback")
    photo = upload_photo(client, headers, album["id"], "fallback.jpg")
    _finish_cleaning(client, headers, album["id"], [photo["id"]])

    analysis = client.post(f"/api/v1/albums/{album['id']}/theme-analysis", headers=headers)
    assert analysis.status_code == 202
    run_task_worker(analysis.json()["data"]["task"])
    workspace = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    assert workspace["profile"]["fallback_used"] is True
    assert [item["id"] for item in workspace["profile"]["candidates"]] == ["complete_record"]


def test_theme_review_can_reselect_an_existing_candidate(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "theme_curation_enabled", True)
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(ChapterFeatureService, "extract", _fake_feature_extract)
    monkeypatch.setattr("app.services.theme_curation_task_runner.generate_theme_candidates", _fake_theme_candidates)
    _enable_cross_modal_test_scoring(monkeypatch)

    headers = create_auth_headers(client, username="theme-reselect", password="secret", role="user")
    album = create_album(client, headers, name="Theme Reselect")
    photo = upload_photo(client, headers, album["id"], "meal.jpg")
    _finish_cleaning(client, headers, album["id"], [photo["id"]])

    analysis = client.post(
        f"/api/v1/albums/{album['id']}/theme-analysis",
        json={"custom_theme": "亲友聚会"},
        headers=headers,
    )
    run_task_worker(analysis.json()["data"]["task"])
    workspace = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    candidate = workspace["profile"]["candidates"][0]

    first_selection = client.post(
        f"/api/v1/albums/{album['id']}/theme-selection",
        json={
            "profile_id": workspace["profile"]["id"],
            "candidate_id": candidate["id"],
            "chapter_strategy": candidate["recommended_strategy"],
        },
        headers=headers,
    )
    run_task_worker(first_selection.json()["data"]["task"])

    second_selection = client.post(
        f"/api/v1/albums/{album['id']}/theme-selection",
        json={
            "profile_id": workspace["profile"]["id"],
            "candidate_id": candidate["id"],
            "chapter_strategy": candidate["recommended_strategy"],
        },
        headers=headers,
    )
    assert second_selection.status_code == 202
    assert second_selection.json()["data"]["task"]["id"] != first_selection.json()["data"]["task"]["id"]
    run_task_worker(second_selection.json()["data"]["task"])

    review = client.get(f"/api/v1/albums/{album['id']}/theme-workspace", headers=headers).json()["data"]
    assert review["phase"] == "review_theme_photos"
    assert review["profile"]["title"] == "亲友聚会"
    assert len(review["assessments"]) == 1


def test_theme_relevance_scoring_sends_uncertain_photos_to_review():
    payload = ThemeRelevanceEngine.score_record(
        photo_id="photo",
        taken_at=None,
        feature=None,
        candidate={"id": "candidate-1"},
        query=None,
        calibration=_test_calibration(),
    )
    assert payload["relevance_label"] == "uncertain"
    assert payload["suggested_decision"] == "review"


def test_custom_theme_preserves_input_and_extracts_year(monkeypatch):
    class FakeProvider:
        async def infer_json(self, request):  # noqa: ANN001
            return ProviderResponse(
                payload={
                    "themes": [{
                        "title": "纪念册",
                        "include_concepts": ["camera_photo"],
                        "exclude_concepts": [],
                        "recommended_strategy": "time_first",
                    }],
                },
                raw_text="",
                model=request.model,
                provider="fake",
            )

    monkeypatch.setattr(
        "app.engines.theme_pipeline.get_ai_provider",
        lambda provider: FakeProvider(),
    )
    connection = ProviderConnectionConfig(
        provider="fake",
        api_key="test",
        api_url=None,
        model="test-model",
        source="test",
    )
    candidates, _ = asyncio.run(
        generate_theme_candidates(
            {"photo_count": 1},
            images=[],
            candidate_count=1,
            provider_connection=connection,
            custom_theme="2026年度纪念册",
        )
    )
    assert candidates[0]["title"] == "2026年度纪念册"
    assert candidates[0]["constraints"]["time"]["years"] == [2026]


def test_custom_theme_year_excludes_photos_from_other_years():
    payload = ThemeRelevanceEngine.score_record(
        photo_id="photo",
        taken_at=datetime(2025, 12, 31, tzinfo=UTC),
        feature={
            "embedding": [1.0, 0.0],
            "embedding_provider": "test-embedding-provider",
            "embedding_model": "test-embedding",
            "embedding_dimension": 2,
        },
        candidate={"id": "candidate-1", "explicit_constraints": {"time": {"years": [2026]}}},
        query=asyncio.run(_fake_theme_query(None, None, connection=None, dimension=2)),
        calibration=_test_calibration(),
    )
    assert payload["suggested_decision"] == "exclude"
    assert "outside_requested_year" in payload["reasons_json"]


def test_year_constraint_with_missing_capture_time_requires_review():
    payload = ThemeRelevanceEngine.score_record(
        photo_id="photo",
        taken_at=None,
        feature={
            "embedding": [1.0, 0.0],
            "embedding_provider": "test-embedding-provider",
            "embedding_model": "test-embedding",
            "embedding_dimension": 2,
        },
        candidate={"id": "candidate-1", "explicit_constraints": {"time": {"years": [2026]}}},
        query=asyncio.run(_fake_theme_query(None, None, connection=None, dimension=2)),
        calibration=_test_calibration(),
    )
    assert payload["suggested_decision"] == "review"
    assert "missing_capture_time" in payload["reasons_json"]


def test_theme_constraints_parse_year_ranges_and_dates():
    constraints = normalize_theme_constraints({}, custom_theme="2024-2026家庭旅行 2025年05月01日-2025年05月03日")
    assert constraints["time"]["years"] == [2024, 2025, 2026]
    assert constraints["time"]["start_date"] == "2025-05-01"
    assert constraints["time"]["end_date"] == "2025-05-03"


def test_theme_candidate_schema_normalizes_model_output():
    payload = ThemeCandidateBatchOutput.model_validate({
        "themes": [{
            "title": f"  烧烤聚会{'会' * 100} English  ",
            "summary": "这个字段应被忽略",
            "include_concepts": [f"concept-{index}" for index in range(9)],
            "exclude_concepts": [f"excluded-{index}" for index in range(10)],
            "recommended_strategy": "unexpected_strategy",
        }],
    })

    assert payload.themes[0].title == "烧烤聚会会会会会"
    assert len(payload.themes[0].include_concepts) == 8
    assert len(payload.themes[0].exclude_concepts) == 8
    assert payload.themes[0].recommended_strategy == "balanced"

    with pytest.raises(ValueError, match="Chinese characters"):
        ThemeCandidateBatchOutput.model_validate({"themes": [{"title": "Barbecue"}]})


def test_query_spec_rejects_album_concepts_not_entailed_by_raw_theme(monkeypatch):
    class FakeProvider:
        async def infer_json(self, request):  # noqa: ANN001
            del request
            return ProviderResponse(
                payload={"concepts": [
                    {"concept": "coast", "entailed": True},
                    {"concept": "park", "entailed": False},
                    {"concept": "garden", "entailed": False},
                ]},
                raw_text="",
                model="test-verifier",
                provider="fake",
            )

    monkeypatch.setattr("app.engines.theme_pipeline.get_ai_provider", lambda provider: FakeProvider())
    result = asyncio.run(build_theme_query_spec(
        {
            "constraints": {
                "include_concepts": ["coast", "park", "garden"],
                "exclude_concepts": ["document"],
            },
        },
        raw_theme="coastal travel",
        connection=ProviderConnectionConfig(
            provider="fake",
            api_key="test",
            api_url=None,
            model="test-verifier",
            source="test",
        ),
    ))
    assert result["entailed_concepts"] == ["coast"]
    assert result["negative_concepts"] == ["document"]


def test_non_custom_candidate_does_not_reuse_original_custom_theme():
    assert selected_theme_text(
        {"title": "怀旧零食铺", "source": "ai"},
        "江边旅行",
    ) == "怀旧零食铺"
    assert selected_theme_text(
        {"title": "候选标题", "source": "custom"},
        "用户原始主题",
    ) == "用户原始主题"
