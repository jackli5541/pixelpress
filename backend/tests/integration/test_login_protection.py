from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.services.login_protection_service import LoginProtectionService


def test_login_locks_after_repeated_failures(client):
    settings = get_settings()
    username = "lock-user"
    password = "secret"
    register = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert register.status_code == 200

    for _ in range(settings.auth_login_max_failures):
        response = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-pass"})
        assert response.status_code == 401

    locked = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert locked.status_code == 429
    assert locked.json()["message"] == "too many login attempts, please try again later"


def test_login_success_clears_failures(client):
    username = "recovery-user"
    password = "secret"
    register = client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert register.status_code == 200

    failed = client.post("/api/v1/auth/login", json={"username": username, "password": "wrong-pass"})
    assert failed.status_code == 401

    succeeded = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert succeeded.status_code == 200

    protection = LoginProtectionService()
    user_fail_key = protection._user_fail_key(username)
    ip_fail_key = protection._ip_fail_key("testclient")
    async def read_keys():
        try:
            return await protection.redis.mget(user_fail_key, ip_fail_key)
        finally:
            await protection.redis.aclose()

    assert asyncio.run(read_keys()) == [None, None]
