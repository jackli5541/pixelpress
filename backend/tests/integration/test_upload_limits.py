from __future__ import annotations

from app.core.config import get_settings
from .helpers import VALID_JPEG_BYTES, create_album, create_auth_headers


def test_upload_rejects_too_many_files(client, monkeypatch):
    headers = create_auth_headers(client, username="limit-owner", password="secret", role="user")
    album = create_album(client, headers, name="Too Many Files")
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_max_files_per_request", 1)

    response = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[
            ("files", ("a.jpg", VALID_JPEG_BYTES, "image/jpeg")),
            ("files", ("b.jpg", VALID_JPEG_BYTES, "image/jpeg")),
        ],
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["message"] == "too many files in upload request"


def test_upload_rejects_single_file_too_large(client, monkeypatch):
    headers = create_auth_headers(client, username="single-large-owner", password="secret", role="user")
    album = create_album(client, headers, name="Single Large File")
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_max_file_size_bytes", 10)

    response = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[("files", ("a.jpg", VALID_JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["uploaded"] == []
    assert payload["rejected"][0]["reason"] == "file too large"


def test_upload_rejects_batch_too_large(client, monkeypatch):
    headers = create_auth_headers(client, username="batch-large-owner", password="secret", role="user")
    album = create_album(client, headers, name="Batch Large File")
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_max_file_size_bytes", 10_000)
    monkeypatch.setattr(settings, "upload_max_batch_size_bytes", 20)

    response = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[("files", ("a.jpg", VALID_JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 413
    assert response.json()["message"] == "upload batch too large"


def test_upload_rejects_invalid_dimensions_when_pixel_limit_tight(client, monkeypatch):
    headers = create_auth_headers(client, username="pixel-owner", password="secret", role="user")
    album = create_album(client, headers, name="Pixel Limit")
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_max_file_size_bytes", 10_000)
    monkeypatch.setattr(settings, "upload_max_batch_size_bytes", 10_000)
    monkeypatch.setattr(settings, "upload_max_image_pixels", 1)

    response = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[("files", ("a.jpg", VALID_JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["uploaded"] == []
    assert payload["rejected"][0]["reason"] == "image exceeds pixel limit"
