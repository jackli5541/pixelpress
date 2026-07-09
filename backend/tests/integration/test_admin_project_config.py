from __future__ import annotations

from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from app.ai.types import ProviderResponse
from app.core.config import get_settings
from .helpers import create_auth_headers


def test_public_register_cannot_escalate_to_admin(client):
    response = client.post("/api/v1/auth/register", json={"username": "plain", "password": "secret"})
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "user"


def test_admin_can_manage_project_ai_configs(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_api_key", "fallback-key")
    monkeypatch.setattr(settings, "llm_api_url", "https://example.com")

    async def fake_infer(self, request):  # noqa: ANN001
        return ProviderResponse(
            payload={"status": "ok"},
            raw_text='{"status":"ok"}',
            model=request.model,
            provider="openai_compatible",
            debug={"tested": True},
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "infer_json", fake_infer)

    admin_headers = create_auth_headers(client, username="admin-config", password="secret", role="admin")
    user_headers = create_auth_headers(client, username="owner-config", password="secret", role="user")

    user_me = client.get("/api/v1/users/me", headers=user_headers)
    user_id = user_me.json()["data"]["id"]

    project_response = client.post(
        "/api/v1/admin/projects",
        json={"user_id": user_id, "name": "Client A"},
        headers=admin_headers,
    )
    assert project_response.status_code == 200
    project = project_response.json()["data"]

    create_config = client.post(
        f"/api/v1/admin/projects/{project['id']}/ai-configs",
        json={
            "provider_type": "openai_compatible",
            "base_url": "https://relay.example.com/v1",
            "model": "gpt-5.4-mini",
            "api_key": "sk-test-12345678",
            "priority": 10,
        },
        headers=admin_headers,
    )
    assert create_config.status_code == 200
    created_config = create_config.json()["data"]
    assert created_config["api_key_masked"].startswith("sk-t")

    list_configs = client.get(f"/api/v1/admin/projects/{project['id']}/ai-configs", headers=admin_headers)
    assert list_configs.status_code == 200
    assert list_configs.json()["data"][0]["id"] == created_config["id"]

    test_config = client.post(f"/api/v1/admin/ai-configs/{created_config['id']}/test", headers=admin_headers)
    assert test_config.status_code == 200
    assert test_config.json()["data"]["payload"]["status"] == "ok"

    logs = client.get(f"/api/v1/admin/audit-logs?project_id={project['id']}", headers=admin_headers)
    assert logs.status_code == 200
    assert len(logs.json()["data"]) >= 2

    forbidden = client.get("/api/v1/admin/projects", headers=user_headers)
    assert forbidden.status_code == 403
