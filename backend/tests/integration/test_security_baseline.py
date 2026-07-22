from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_requires_auth_secret_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            auth_secret_key="change-me-in-production",
            SECRETS_MASTER_KEY="x" * 32,
            cors_allow_origins=["https://example.com"],
        )
    assert "AUTH_SECRET_KEY must be set for production" in str(exc_info.value)


def test_production_requires_secrets_master_key() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            auth_secret_key="a" * 32,
            SECRETS_MASTER_KEY=None,
            cors_allow_origins=["https://example.com"],
        )
    assert "SECRETS_MASTER_KEY must be set for production" in str(exc_info.value)


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            auth_secret_key="a" * 32,
            SECRETS_MASTER_KEY="b" * 32,
            cors_allow_origins=["*"],
        )
    assert "Wildcard CORS is not allowed in production" in str(exc_info.value)


def test_production_requires_full_http_origins() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            auth_secret_key="a" * 32,
            SECRETS_MASTER_KEY="b" * 32,
            cors_allow_origins=["example.com"],
        )
    assert "CORS_ALLOW_ORIGINS must contain full http/https origins" in str(exc_info.value)


def test_production_rejects_same_secret_keys() -> None:
    shared = "z" * 32
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            app_env="production",
            auth_secret_key=shared,
            SECRETS_MASTER_KEY=shared,
            cors_allow_origins=["https://example.com"],
        )
    assert "AUTH_SECRET_KEY and SECRETS_MASTER_KEY must be different" in str(exc_info.value)
