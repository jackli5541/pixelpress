from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException, status

from app.services.secret_service import SecretService


class RenderAccessService:
    def __init__(self) -> None:
        self.secret_service = SecretService()

    def issue_photo_preview_token(
        self,
        *,
        album_id: str,
        photo_id: str,
        render_revision: int,
        ttl_seconds: int = 300,
    ) -> tuple[str, int]:
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        expires_ts = int(expires_at.timestamp())
        payload = {
            "album_id": album_id,
            "photo_id": photo_id,
            "render_revision": render_revision,
            "exp": expires_ts,
        }
        token = self.secret_service.encrypt_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        return token, expires_ts

    def build_photo_preview_url(
        self,
        *,
        album_id: str,
        photo_id: str,
        render_revision: int,
        ttl_seconds: int = 300,
    ) -> str:
        token, expires_ts = self.issue_photo_preview_token(
            album_id=album_id,
            photo_id=photo_id,
            render_revision=render_revision,
            ttl_seconds=ttl_seconds,
        )
        return (
            f"/api/v1/render-assets/albums/{album_id}/photos/{photo_id}"
            f"?token={quote(token, safe='')}&exp={expires_ts}&rev={render_revision}"
        )

    def verify_photo_preview_token(
        self,
        *,
        album_id: str,
        photo_id: str,
        render_revision: int,
        token: str,
        exp: int,
    ) -> None:
        if int(datetime.now(UTC).timestamp()) > exp:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="preview token expired")
        try:
            payload = json.loads(self.secret_service.decrypt_text(token))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid preview token") from exc

        if (
            payload.get("album_id") != album_id
            or payload.get("photo_id") != photo_id
            or int(payload.get("render_revision", -1)) != render_revision
            or int(payload.get("exp", -1)) != exp
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid preview token")
