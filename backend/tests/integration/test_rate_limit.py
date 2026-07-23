from __future__ import annotations

from app.core.config import get_settings
from .helpers import VALID_JPEG_BYTES, create_album, create_auth_headers


def test_login_rate_limit_returns_429(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_login", "2/minute")

    register = client.post("/api/v1/auth/register", json={"username": "ratelimit-user", "password": "secret"})
    assert register.status_code == 200

    first = client.post("/api/v1/auth/login", json={"username": "ratelimit-user", "password": "wrong-pass"})
    second = client.post("/api/v1/auth/login", json={"username": "ratelimit-user", "password": "wrong-pass"})
    limited = client.post("/api/v1/auth/login", json={"username": "ratelimit-user", "password": "wrong-pass"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert limited.status_code == 429


def test_upload_rate_limit_returns_429(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_upload", "1/minute")

    headers = create_auth_headers(client, username="upload-rate-user", password="secret", role="user")
    album = create_album(client, headers, name="Upload Rate")
    other_album = create_album(client, headers, name="Upload Rate Independent Album")

    first = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[("files", ("a.jpg", VALID_JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    other_album_first = client.post(
        f"/api/v1/albums/{other_album['id']}/photos/upload",
        files=[("files", ("other.jpg", VALID_JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )
    limited = client.post(
        f"/api/v1/albums/{album['id']}/photos/upload",
        files=[("files", ("b.jpg", VALID_JPEG_BYTES, "image/jpeg"))],
        headers=headers,
    )

    assert first.status_code == 200
    assert other_album_first.status_code == 200
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    assert limited.headers["X-RateLimit-Limit"] == "1"
    assert limited.headers["X-RateLimit-Remaining"] == "0"
    assert int(limited.headers["X-RateLimit-Reset"]) > 0


def test_export_rate_limit_returns_429(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_export", "1/minute")

    headers = create_auth_headers(client, username="export-rate-admin", password="secret", role="admin")
    album = create_album(client, headers, name="Export Rate")

    first = client.post(f"/api/v1/albums/{album['id']}/export", headers=headers)
    limited = client.post(f"/api/v1/albums/{album['id']}/export", headers=headers)

    assert first.status_code in {400, 202}
    assert limited.status_code == 429
