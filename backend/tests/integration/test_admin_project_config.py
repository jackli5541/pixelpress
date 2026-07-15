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

    project_response = client.get("/api/v1/users/me/projects", headers=user_headers)
    assert project_response.status_code == 200
    project = project_response.json()["data"][0]

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

    defaults = client.get("/api/v1/admin/ai-default-configs", headers=admin_headers)
    assert defaults.status_code == 200
    assert {item["stage"] for item in defaults.json()["data"]} == {"chapter", "layout"}
    update_default = client.patch(
        "/api/v1/admin/ai-default-configs/chapter",
        json={"model": "gpt-5.4-mini", "api_key": "sk-default-12345678"},
        headers=admin_headers,
    )
    assert update_default.status_code == 200
    assert update_default.json()["data"]["api_key_masked"].startswith("sk-d")
    test_default = client.post("/api/v1/admin/ai-default-configs/chapter/test", headers=admin_headers)
    assert test_default.status_code == 200
    assert test_default.json()["data"]["payload"]["status"] == "ok"

    forbidden = client.get("/api/v1/admin/projects", headers=user_headers)
    assert forbidden.status_code == 403
