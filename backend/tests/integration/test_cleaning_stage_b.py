from __future__ import annotations

from io import BytesIO

from PIL import Image

from app.engines.cleaning_engine.service import build_cleaning_result
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


def test_complete_link_does_not_merge_transitive_chain():
    result = build_cleaning_result(
        "album",
        [_analysis("a", "0000000000000000"), _analysis("b", "000000000000000f"), _analysis("c", "00000000000000ff")],
        auto_exclude_exact=False,
    )
    assert len(result["groups"]) == 1
    assert {member["photo_id"] for member in result["groups"][0]["members"]} in ({"a", "b"}, {"b", "c"})


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
