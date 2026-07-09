from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Any

import jwt

from app.core.config import get_settings

settings = get_settings()


def create_access_token(subject: str, role: str = "user") -> str:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.auth_access_token_exp_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.auth_secret_key, algorithm=settings.auth_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.auth_secret_key, algorithms=[settings.auth_algorithm])
