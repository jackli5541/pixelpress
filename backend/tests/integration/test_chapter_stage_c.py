from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.ai.types import ImagePayload
from app.core.config import get_settings
from app.db import session as db_session
from app.engines.chapter_engine.features import time_range_label
from app.engines.chapter_engine.representatives import select_representative_photos
from app.models.chapter import Chapter
from app.repositories.chapter_repo import ChapterRepository
from app.services.serializers import serialize_chapter
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


def test_openai_provider_serializes_multimodal_image_block():
    block = OpenAICompatibleProvider._image_content(
        ImagePayload(media_type="image/jpeg", data_base64="YWJj", filename="representative.jpg")
    )
    assert block == {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,YWJj", "detail": "low"},
    }


def _photo(
    photo_id: str,
    taken_at: str | None,
    *,
    latitude: float | None = 30.0,
    longitude: float | None = 120.0,
    tags: list[str] | None = None,
    quality: float = 8.0,
    phash: str | None = None,
    histogram_offset: int = 0,
) -> dict:
    histogram = [0.0] * 48
    histogram[histogram_offset % 48] = 1.0
    return {
        "id": photo_id,
        "filename": f"{photo_id}.jpg",
        "taken_at": taken_at,
        "uploaded_at": "2026-07-16T00:00:00+00:00",
        "gps_latitude": latitude,
        "gps_longitude": longitude,
        "scene_tags": tags or [],
        "quality_score": quality,
        "perceptual_hash": phash,
        "cleaning_features": {"color_histogram": histogram},
    }


def test_time_range_label_preserves_stage_c_date_formats():
    assert time_range_label([_photo("same-day", "2026-01-02T09:00:00")]) == "2026年1月2日"
    assert time_range_label([
        _photo("month-a", "2026-01-02T09:00:00"),
        _photo("month-b", "2026-01-31T09:00:00"),
    ]) == "2026年1月2-31日"
    assert time_range_label([
        _photo("cross-month-a", "2026-01-31T09:00:00"),
        _photo("cross-month-b", "2026-02-01T09:00:00"),
    ]) == "2026年1-2月"
    assert time_range_label([
        _photo("cross-year-a", "2025-12-31T09:00:00"),
        _photo("cross-year-b", "2026-01-01T09:00:00"),
    ]) == "2025-2026"
    assert time_range_label([_photo("unknown", None)]) == "未知时间"


def test_representative_selection_prefers_quality_and_rejects_near_duplicate():
    photos = [
        _photo("best", "2026-01-01T10:00:00", quality=9.5, phash="0000000000000000", tags=["beach"]),
        _photo("copy", "2026-01-01T10:05:00", quality=9.0, phash="0000000000000001", tags=["beach"]),
        _photo("different", "2026-01-01T15:00:00", quality=8.0, phash="ffffffffffffffff", tags=["dinner"], histogram_offset=12),
    ]
    selected = select_representative_photos(photos)
    assert selected[0] == "best"
    assert "copy" not in selected
    assert "different" in selected


async def _chapter_model(chapter_id: str) -> Chapter:
    async with db_session.AsyncSessionFactory() as session:
        return (await session.execute(select(Chapter).where(Chapter.id == chapter_id))).scalar_one()


async def _persist_hierarchical_chapter(album_id: str, photo_ids: list[str]) -> dict:
    async with db_session.AsyncSessionFactory() as session:
        chapter = await ChapterRepository(session).create_chapter(
            {
                "album_id": album_id,
                "name": "城市漫步",
                "description": "同一事件中的两个活动阶段",
                "order_index": 0,
                "clustering_source": "algorithm",
                "clustering_algorithm_version": "c7-embedding-sequential-v1",
                "clustering_quality": 0.88,
                "clustering_needs_review": False,
                "clustering_explanation": {"strategy": "balanced", "selected_k": 1},
            },
            photo_ids,
            segments=[
                {
                    "name": "抵达",
                    "description": "上午",
                    "segment_type": "activity",
                    "photo_ids": [photo_ids[0]],
                    "clustering_quality": 0.9,
                    "clustering_needs_review": False,
                    "clustering_explanation": {"selected_k": 2},
                },
                {
                    "name": "晚餐",
                    "description": "晚上",
                    "segment_type": "activity",
                    "photo_ids": [photo_ids[1]],
                    "clustering_quality": 0.86,
                    "clustering_needs_review": False,
                    "clustering_explanation": {"selected_k": 2},
                },
            ],
        )
        await session.commit()
        loaded = await ChapterRepository(session).get_chapter(album_id, chapter.id)
        assert loaded is not None
        return serialize_chapter(loaded)


def test_hierarchical_segments_persist_and_serialize(client):
    headers = create_auth_headers(client, username="stage-c-hierarchy", password="secret", role="user")
    album = create_album(client, headers, name="Hierarchical Stage C")
    first = upload_photo(client, headers, album["id"], "arrival.jpg")
    second = upload_photo(client, headers, album["id"], "dinner.jpg")

    chapter = asyncio.run(_persist_hierarchical_chapter(album["id"], [first["id"], second["id"]]))

    assert chapter["photo_ids"] == [first["id"], second["id"]]
    assert [segment["photo_ids"] for segment in chapter["segments"]] == [[first["id"]], [second["id"]]]
    assert chapter["segments"][1]["clustering"]["quality_score"] == 0.86


def test_rebuild_requires_confirmation_and_manual_move_invalidates_clustering(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "theme_curation_enabled", False)
    headers = create_auth_headers(client, username="stage-c-owner", password="secret", role="user")
    album = create_album(client, headers, name="Stage C Album")
    first = upload_photo(client, headers, album["id"], "first.jpg")
    second = upload_photo(client, headers, album["id"], "second.jpg")

    queued = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert queued.status_code == 202
    run_task_worker(queued.json()["data"]["task"])
    chapters = client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers).json()["data"]
    assert chapters[0]["clustering"]["algorithm_version"] == "c1-events-v1"
    assert len(chapters[0]["segments"]) == 1
    assert chapters[0]["segments"][0]["photo_ids"] == chapters[0]["photo_ids"]

    invalid_granularity = client.post(
        f"/api/v1/albums/{album['id']}/cluster",
        json={"confirm_rebuild": True, "granularity": 3},
        headers=headers,
    )
    assert invalid_granularity.status_code == 422

    blocked = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["data"]["message"] == "chapter rebuild confirmation required"

    manual = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "手工章节", "photo_ids": []},
        headers=headers,
    ).json()["data"]
    moved = client.post(
        f"/api/v1/albums/{album['id']}/chapters/move-photos",
        json={"photo_ids": [second["id"]], "target_chapter_id": manual["id"]},
        headers=headers,
    )
    assert moved.status_code == 200
    updated = asyncio.run(_chapter_model(manual["id"]))
    assert updated.clustering_source == "user"
    assert updated.clustering_quality is None

    confirmed = client.post(
        f"/api/v1/albums/{album['id']}/cluster",
        json={"confirm_rebuild": True, "granularity": 1},
        headers=headers,
    )
    assert confirmed.status_code == 202
    confirmed_task = confirmed.json()["data"]["task"]
    assert confirmed_task["task_params"]["granularity"] == 1
    run_task_worker(confirmed_task)
    detail = client.get(f"/api/v1/albums/{album['id']}/tasks/{confirmed_task['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["data"]["task_status"] == "succeeded"


def test_chapter_photo_ids_must_belong_to_album(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "theme_curation_enabled", False)
    headers = create_auth_headers(client, username="stage-c-photo-scope", password="secret", role="user")
    album = create_album(client, headers, name="Photo Scope A")
    other_album = create_album(client, headers, name="Photo Scope B")
    local_photo = upload_photo(client, headers, album["id"], "local.jpg")
    foreign_photo = upload_photo(client, headers, other_album["id"], "foreign.jpg")

    created = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "Scope", "photo_ids": [foreign_photo["id"]]},
        headers=headers,
    )
    assert created.status_code == 422
    assert created.json()["data"]["code"] == "invalid_photo_ids"

    chapter = client.post(
        f"/api/v1/albums/{album['id']}/chapters",
        json={"name": "Scope", "photo_ids": [local_photo["id"]]},
        headers=headers,
    ).json()["data"]
    updated = client.patch(
        f"/api/v1/albums/{album['id']}/chapters/{chapter['id']}",
        json={"photo_ids": [foreign_photo["id"]]},
        headers=headers,
    )
    assert updated.status_code == 422

    moved = client.post(
        f"/api/v1/albums/{album['id']}/chapters/move-photos",
        json={"photo_ids": [foreign_photo["id"]], "target_chapter_id": chapter["id"]},
        headers=headers,
    )
    assert moved.status_code == 422
