from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.db import session as db_session
from app.engines.cleaning_engine.local_analyzer import _quality_suggestion
from app.engines.cleaning_engine.service import MAX_DUPLICATE_CANDIDATES_PER_PHOTO, _candidate_pairs, build_cleaning_result
from app.models.photo import Photo
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


def _jpeg_bytes(color: tuple[int, int, int], size: tuple[int, int] = (64, 64), quality: int = 90) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=color).save(output, format="JPEG", quality=quality)
    return output.getvalue()


def _analysis(photo_id: str, phash: str) -> dict:
    return {
        "photo_id": photo_id,
        "content_sha256": photo_id,
        "perceptual_hash": phash,
        "analysis_version": "test",
        "quality_score": 7.0,
        "suggestion": "keep",
        "confidence": 0.9,
        "issues": [],
        "features": {
            "sharpness": {"score": 0.7},
            "exposure": {"score": 0.7},
            "resolution": {"score": 0.7, "width": 1000, "height": 1000},
            "composition": {"aspect_ratio": 1.0, "orientation": "square"},
            "color_histogram": [0.0] * 48,
        },
        "taken_at": None,
        "device_model": None,
        "uploaded_at": None,
    }


async def _set_cleaning_state(photo_id: str, *, suggestion: str | None, decision: str | None = None) -> None:
    async with db_session.AsyncSessionFactory() as session:
        photo = (await session.execute(select(Photo).where(Photo.id == photo_id))).scalar_one()
        photo.cleaning_suggestion = suggestion
        photo.cleaning_decision = decision
        photo.cleaning_decision_source = "user" if decision else None
        await session.commit()


def test_complete_link_does_not_merge_transitive_chain():
    result = build_cleaning_result(
        "album",
        [_analysis("a", "0000000000000000"), _analysis("b", "000000000000000f"), _analysis("c", "00000000000000ff")],
        auto_exclude_exact=False,
    )
    assert len(result["groups"]) == 1
    assert {member["photo_id"] for member in result["groups"][0]["members"]} in ({"a", "b"}, {"b", "c"})


def test_duplicate_candidate_scope_is_bounded_for_large_albums():
    analyses = [_analysis(f"photo-{index}", f"{index:016x}") for index in range(2000)]
    pairs = _candidate_pairs(analyses)
    counts = [0] * len(analyses)
    for left, right in pairs:
        counts[left] += 1
        counts[right] += 1

    assert len(pairs) <= len(analyses) * MAX_DUPLICATE_CANDIDATES_PER_PHOTO // 2
    assert max(counts) <= MAX_DUPLICATE_CANDIDATES_PER_PHOTO


def test_quality_discard_boundary_requires_two_severe_issues_below_three():
    assert _quality_suggestion(2.99, 2) == ("remove", 0.9, True)
    assert _quality_suggestion(3.0, 2) == ("review", 0.75, False)
    assert _quality_suggestion(2.99, 1) == ("review", 0.75, False)


def test_exact_subgroup_auto_excludes_copy_when_near_image_is_group_preferred():
    first = _analysis("a", "0000000000000000")
    copy = _analysis("b", "0000000000000000")
    near = _analysis("c", "0000000000000001")
    first["content_sha256"] = "same"
    copy["content_sha256"] = "same"
    near["quality_score"] = 9.0
    result = build_cleaning_result("album", [first, copy, near], auto_exclude_exact=True)
    assert result["groups"][0]["preferred_photo_id"] == "c"
    excluded = [member for member in result["groups"][0]["members"] if member["auto_excluded"]]
    assert len(excluded) == 1
    assert excluded[0]["photo_id"] in {"a", "b"}


def test_same_file_size_different_content_is_not_exact_duplicate(client):
    headers = create_auth_headers(client, username="clean-size-owner", password="secret", role="user")
    album = create_album(client, headers, name="Same Size Album")
    left = _jpeg_bytes((200, 20, 20))
    right = _jpeg_bytes((20, 20, 200))
    if len(left) < len(right):
        left += b"\x00" * (len(right) - len(left))
    elif len(right) < len(left):
        right += b"\x00" * (len(left) - len(right))
    upload_photo(client, headers, album["id"], "red.jpg", left)
    upload_photo(client, headers, album["id"], "blue.jpg", right)

    queued = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    run_task_worker(queued.json()["data"]["task"])
    results = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    assert all(group["group_type"] != "exact" for group in results["groups"])


def test_clear_quality_discard_is_automatic_and_recoverable(client):
    headers = create_auth_headers(client, username="clean-quality-owner", password="secret", role="user")
    album = create_album(client, headers, name="Clear Quality Discard")
    photo = upload_photo(client, headers, album["id"], "unusable.jpg", _jpeg_bytes((0, 0, 0)))

    queued = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    run_task_worker(queued.json()["data"]["task"])
    result = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    analyzed = next(item for item in result["items"] if item["id"] == photo["id"])
    assert analyzed["cleaning"]["suggestion"] == "remove"
    assert analyzed["cleaning"]["decision"] == "remove"
    assert analyzed["cleaning"]["decision_source"] == "system_quality_threshold"

    restored = client.patch(
        f"/api/v1/albums/{album['id']}/clean/decisions",
        json={"photo_ids": [photo["id"]], "decision": "keep"},
        headers=headers,
    )
    assert restored.status_code == 200


def test_exact_duplicate_auto_exclusion_is_recoverable_and_user_choice_survives_rerun(client):
    headers = create_auth_headers(client, username="clean-restore-owner", password="secret", role="user")
    album = create_album(client, headers, name="Recoverable Cleaning")
    content = _jpeg_bytes((120, 140, 160), size=(900, 900))
    upload_photo(client, headers, album["id"], "copy-a.jpg", content)
    upload_photo(client, headers, album["id"], "copy-b.jpg", content)

    queued = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    assert queued.status_code == 202
    task = queued.json()["data"]["task"]
    run_task_worker(task)
    task_detail = client.get(f"/api/v1/albums/{album['id']}/tasks/{task['id']}", headers=headers).json()["data"]
    assert task_detail["task_status"] == "succeeded", {
        "error_code": task_detail.get("error_code"),
        "error_message": task_detail.get("error_message"),
        "debug_payload": task_detail.get("debug_payload"),
    }

    result_response = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers)
    assert result_response.status_code == 200
    result = result_response.json()["data"]
    assert result["summary"]["duplicate_groups"] == 1
    assert result["groups"][0]["group_type"] == "exact"
    excluded = [photo for photo in result["items"] if photo["cleaning"]["excluded"]]
    assert len(excluded) == 1
    assert excluded[0]["cleaning"]["decision_source"] == "system_exact_duplicate"

    restore = client.patch(
        f"/api/v1/albums/{album['id']}/clean/decisions",
        json={"photo_ids": [excluded[0]["id"]], "decision": "keep"},
        headers=headers,
    )
    assert restore.status_code == 200

    rerun = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    assert rerun.status_code == 202
    run_task_worker(rerun.json()["data"]["task"])
    rerun_result = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    restored = next(photo for photo in rerun_result["items"] if photo["id"] == excluded[0]["id"])
    assert restored["cleaning"]["decision"] == "keep"
    assert restored["cleaning"]["decision_source"] == "user"


def test_reset_clears_system_decisions_but_preserves_user_decisions(client):
    headers = create_auth_headers(client, username="clean-reset-owner", password="secret", role="user")
    album = create_album(client, headers, name="Reset Cleaning")
    content = _jpeg_bytes((80, 100, 120), size=(900, 900))
    for filename in ("copy-a.jpg", "copy-b.jpg", "copy-c.jpg"):
        upload_photo(client, headers, album["id"], filename, content)

    queued = client.post(f"/api/v1/albums/{album['id']}/clean", headers=headers)
    run_task_worker(queued.json()["data"]["task"])
    initial = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    system_excluded = [item for item in initial["items"] if item["cleaning"]["decision_source"] == "system_exact_duplicate"]
    assert len(system_excluded) == 2

    user_photo, system_photo = system_excluded
    updated = client.patch(
        f"/api/v1/albums/{album['id']}/clean/decisions",
        json={"photo_ids": [user_photo["id"]], "decision": "keep"},
        headers=headers,
    )
    assert updated.status_code == 200

    reset = client.post(f"/api/v1/albums/{album['id']}/clean/reset", json={}, headers=headers)
    assert reset.status_code == 200
    assert reset.json()["data"]["status"] == "uploaded"

    result = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    items = {item["id"]: item for item in result["items"]}
    assert items[user_photo["id"]]["cleaning"]["decision"] == "keep"
    assert items[user_photo["id"]]["cleaning"]["decision_source"] == "user"
    assert items[system_photo["id"]]["cleaning"]["decision"] is None
    assert items[system_photo["id"]]["cleaning"]["decision_source"] is None


def test_cleaning_decision_legacy_patch_maps_to_user_decision(client):
    headers = create_auth_headers(client, username="clean-legacy-owner", password="secret", role="user")
    album = create_album(client, headers, name="Legacy Decision")
    photo = upload_photo(client, headers, album["id"], "legacy.jpg", _jpeg_bytes((30, 60, 90)))
    response = client.patch(
        f"/api/v1/albums/{album['id']}/photos/{photo['id']}",
        json={"cleaning_recommendation": "remove"},
        headers=headers,
    )
    assert response.status_code == 200
    updated = response.json()["data"]
    assert updated["cleaning_recommendation"] == "remove"
    assert updated["cleaning"]["decision"] == "remove"
    assert updated["cleaning"]["decision_source"] == "user"


def test_review_status_and_summary_follow_effective_user_decision(client):
    headers = create_auth_headers(client, username="review-status-owner", password="secret", role="user")
    album = create_album(client, headers, name="Review Status")
    photo = upload_photo(client, headers, album["id"], "review.jpg", _jpeg_bytes((80, 90, 100)))
    asyncio.run(_set_cleaning_state(photo["id"], suggestion="review"))
    pending = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    pending_photo = next(item for item in pending["items"] if item["id"] == photo["id"])
    assert pending_photo["cleaning"]["suggestion"] == "review"
    assert pending_photo["cleaning"]["review_status"] == "pending_review"
    assert pending["summary"]["pending_review"] == 1

    kept = client.patch(
        f"/api/v1/albums/{album['id']}/clean/decisions",
        json={"photo_ids": [photo["id"]], "decision": "keep"},
        headers=headers,
    )
    assert kept.status_code == 200
    resolved = client.get(f"/api/v1/albums/{album['id']}/clean/results", headers=headers).json()["data"]
    resolved_photo = next(item for item in resolved["items"] if item["id"] == photo["id"])
    assert resolved_photo["cleaning"]["suggestion"] == "review"
    assert resolved_photo["cleaning"]["review_status"] == "kept"
    assert resolved["summary"]["pending_review"] == 0
    assert resolved["summary"]["kept"] == 1


def test_chapter_clustering_requires_review_and_excludes_removed_photos(client):
    headers = create_auth_headers(client, username="chapter-review-owner", password="secret", role="user")
    album = create_album(client, headers, name="Chapter Review Gate")
    kept_photo = upload_photo(client, headers, album["id"], "keep.jpg", _jpeg_bytes((80, 90, 100)))
    removed_photo = upload_photo(client, headers, album["id"], "remove.jpg", _jpeg_bytes((100, 90, 80)))

    queued_before_review = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert queued_before_review.status_code == 202

    asyncio.run(_set_cleaning_state(kept_photo["id"], suggestion="review"))
    asyncio.run(_set_cleaning_state(removed_photo["id"], suggestion="remove"))
    run_task_worker(queued_before_review.json()["data"]["task"])
    stale_task = client.get(
        f"/api/v1/albums/{album['id']}/tasks/{queued_before_review.json()['data']['task']['id']}",
        headers=headers,
    ).json()["data"]
    assert stale_task["task_status"] == "failed"
    assert stale_task["error_code"] == "pending_photo_review"

    blocked = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["data"] == {"message": "pending photo review", "pending_review_count": 2}

    decision = client.patch(
        f"/api/v1/albums/{album['id']}/clean/decisions",
        json={"photo_ids": [kept_photo["id"]], "decision": "keep"},
        headers=headers,
    )
    assert decision.status_code == 200
    decision = client.patch(
        f"/api/v1/albums/{album['id']}/clean/decisions",
        json={"photo_ids": [removed_photo["id"]], "decision": "remove"},
        headers=headers,
    )
    assert decision.status_code == 200

    queued = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert queued.status_code == 202
    run_task_worker(queued.json()["data"]["task"])
    chapters = client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers).json()["data"]
    assert [photo_id for chapter in chapters for photo_id in chapter["photo_ids"]] == [kept_photo["id"]]
