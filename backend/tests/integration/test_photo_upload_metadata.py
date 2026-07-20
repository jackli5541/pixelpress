from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from app.core.config import get_settings
from app.services import photo_service as photo_service_module
from app.services.photo_ingest import ProcessedUploadImage
from .helpers import VALID_JPEG_BYTES, create_album, create_auth_headers, run_task_worker, upload_photo


def _processed_image(*, filename: str, taken_at: datetime | None, taken_timezone: str | None = None, gps_latitude: float | None = None, gps_longitude: float | None = None, device_model: str | None = None) -> ProcessedUploadImage:
    return ProcessedUploadImage(
        filename=filename,
        content_type="image/jpeg",
        content=VALID_JPEG_BYTES,
        width=2,
        height=1,
        taken_at=taken_at,
        taken_timezone=taken_timezone,
        gps_latitude=gps_latitude,
        gps_longitude=gps_longitude,
        device_model=device_model,
    )


def test_upload_persists_capture_metadata_and_normalizes_heic(client, monkeypatch):
    headers = create_auth_headers(client, username="metadata-owner", password="secret", role="user")
    album = create_album(client, headers, name="Metadata Album")
    settings = get_settings()

    processed = _processed_image(
        filename="captured.jpg",
        taken_at=datetime(2024, 5, 6, 7, 8, 9, tzinfo=timezone(timedelta(hours=8))),
        taken_timezone="+08:00",
        gps_latitude=31.2304,
        gps_longitude=121.4737,
        device_model="iPhone 15 Pro",
    )
    monkeypatch.setattr(photo_service_module, "process_uploaded_image", lambda **kwargs: processed)

    response = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[("files", ("captured.heic", VALID_JPEG_BYTES, "image/heic"))],
        headers=headers,
    )
    assert response.status_code == 200

    payload = response.json()["data"]
    assert len(payload["uploaded"]) == 1
    uploaded = payload["uploaded"][0]
    assert uploaded["filename"] == "captured.jpg"
    assert uploaded["content_type"] == "image/jpeg"
    assert uploaded["taken_at"] == "2024-05-05T23:08:09+00:00"
    assert uploaded["taken_timezone"] == "+08:00"
    assert uploaded["gps_latitude"] == 31.2304
    assert uploaded["gps_longitude"] == 121.4737
    assert uploaded["device_model"] == "iPhone 15 Pro"
    assert uploaded["storage_key"].endswith(".jpg")

    stored_path = Path(settings.uploads_dir) / uploaded["storage_key"]
    assert stored_path.exists()

    list_response = client.get(f"/api/v1/albums/{album['id']}/photos", headers=headers)
    assert list_response.status_code == 200
    listed = list_response.json()["data"]["items"][0]
    assert listed["taken_at"] == uploaded["taken_at"]
    assert listed["device_model"] == "iPhone 15 Pro"



def test_delete_photo_endpoint_removes_stored_file(client):
    headers = create_auth_headers(client, username="delete-photo-owner", password="secret", role="user")
    album = create_album(client, headers, name="Delete Photo Album")
    photo = upload_photo(client, headers, album["id"], "delete-target.jpg")
    settings = get_settings()

    stored_path = Path(settings.uploads_dir) / photo["storage_key"]
    assert stored_path.exists()

    delete_response = client.delete(f"/api/v1/albums/{album['id']}/photos/{photo['id']}", headers=headers)
    assert delete_response.status_code == 200

    list_response = client.get(f"/api/v1/albums/{album['id']}/photos", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()["data"]["items"] == []
    assert not stored_path.exists()



def test_rule_cluster_orders_photos_by_taken_at(client, monkeypatch):
    headers = create_auth_headers(client, username="chapter-metadata-owner", password="secret", role="user")
    album = create_album(client, headers, name="Chapter Metadata Album")

    taken_values = [
        _processed_image(filename="a.jpg", taken_at=datetime(2024, 1, 4, tzinfo=UTC)),
        _processed_image(filename="b.jpg", taken_at=datetime(2024, 1, 1, tzinfo=UTC)),
        _processed_image(filename="c.jpg", taken_at=datetime(2024, 1, 3, tzinfo=UTC)),
        _processed_image(filename="d.jpg", taken_at=datetime(2024, 1, 2, tzinfo=UTC)),
    ]

    def fake_process_uploaded_image(**kwargs):
        processed = taken_values.pop(0)
        return replace(processed, filename=kwargs["original_name"])

    monkeypatch.setattr(photo_service_module, "process_uploaded_image", fake_process_uploaded_image)

    photo_a = upload_photo(client, headers, album["id"], "a.jpg")
    photo_b = upload_photo(client, headers, album["id"], "b.jpg")
    photo_c = upload_photo(client, headers, album["id"], "c.jpg")
    photo_d = upload_photo(client, headers, album["id"], "d.jpg")

    cluster_response = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert cluster_response.status_code == 202
    run_task_worker(cluster_response.json()["data"]["task"])

    chapters_response = client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers)
    assert chapters_response.status_code == 200
    chapters = chapters_response.json()["data"]
    assert len(chapters) == 1
    assert chapters[0]["photo_ids"] == [photo_b["id"], photo_d["id"], photo_c["id"], photo_a["id"]]
