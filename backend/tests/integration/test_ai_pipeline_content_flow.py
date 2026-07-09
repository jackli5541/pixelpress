from __future__ import annotations

from app.ai.types import ProviderResponse
from app.core.config import get_settings
from app.ai.openai_compatible_provider import OpenAICompatibleProvider
from .helpers import create_album, create_auth_headers, run_task_worker, upload_photo


async def _fake_infer_json(self, request):  # noqa: ANN001
    if request.model == "cluster-model":
        return ProviderResponse(
            payload={
                "chapters": [
                    {
                        "name": "海边旅行",
                        "description": "围绕海边活动与家庭互动的章节",
                        "photo_ids": ["photo-a", "photo-b", "photo-c"],
                    }
                ]
            },
            raw_text="{}",
            model=request.model,
            provider="openai_compatible",
            debug={"mocked": True},
        )
    return ProviderResponse(
        payload={
            "style_key": "warm_family",
            "page_role": "opening",
            "template_key": "one_large_two_small",
            "ordered_photo_ids": ["photo-c", "photo-a", "photo-b"],
            "title": "海边的第一天",
            "subtitle": "风很轻，光很暖",
            "captions": [
                {"photo_id": "photo-c", "text": "一家人在海边合影"},
                {"photo_id": "photo-a", "text": "孩子踩着浪花奔跑"},
                {"photo_id": "photo-b", "text": "傍晚时分的沙滩"},
            ],
            "confidence": 0.91,
            "reason": "主图突出，次图补充叙事",
            "alternatives": ["grid_3"],
        },
        raw_text="{}",
        model=request.model,
        provider="openai_compatible",
        debug={"mocked": True},
    )


def test_ai_chapter_cluster_and_layout_content_flow(client, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_enabled", True)
    monkeypatch.setattr(settings, "ai_provider_b2", "openai_compatible")
    monkeypatch.setattr(settings, "ai_provider_b3", "openai_compatible")
    monkeypatch.setattr(settings, "ai_mode_b2", "llm")
    monkeypatch.setattr(settings, "ai_mode_b3", "llm")
    monkeypatch.setattr(settings, "ai_model_b2", "cluster-model")
    monkeypatch.setattr(settings, "ai_model_b3", "layout-model")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_api_url", "https://example.com")
    monkeypatch.setattr(OpenAICompatibleProvider, "infer_json", _fake_infer_json)

    headers = create_auth_headers(client, username="ai-owner", password="secret", role="admin")
    album = create_album(client, headers, name="AI 成品相册")

    photo_a = upload_photo(client, headers, album["id"], "a.jpg")
    photo_b = upload_photo(client, headers, album["id"], "b.jpg")
    photo_c = upload_photo(client, headers, album["id"], "c.jpg")

    photo_id_map = {
        "photo-a": photo_a["id"],
        "photo-b": photo_b["id"],
        "photo-c": photo_c["id"],
    }

    async def remapped_infer(self, request):  # noqa: ANN001
        response = await _fake_infer_json(self, request)
        payload = response.payload
        if "chapters" in payload:
            payload = {
                "chapters": [
                    {
                        **payload["chapters"][0],
                        "photo_ids": [photo_id_map[item] for item in payload["chapters"][0]["photo_ids"]],
                    }
                ]
            }
        else:
            payload = {
                **payload,
                "ordered_photo_ids": [photo_id_map[item] for item in payload["ordered_photo_ids"]],
                "captions": [
                    {"photo_id": photo_id_map[item["photo_id"]], "text": item["text"]}
                    for item in payload["captions"]
                ],
            }
        return ProviderResponse(
            payload=payload,
            raw_text=response.raw_text,
            model=response.model,
            provider=response.provider,
            debug=response.debug,
        )

    monkeypatch.setattr(OpenAICompatibleProvider, "infer_json", remapped_infer)

    cluster_response = client.post(f"/api/v1/albums/{album['id']}/cluster", headers=headers)
    assert cluster_response.status_code == 202
    cluster_task = cluster_response.json()["data"]["task"]
    run_task_worker(cluster_task)
    chapters_response = client.get(f"/api/v1/albums/{album['id']}/chapters", headers=headers)
    chapters = chapters_response.json()["data"]
    assert len(chapters) == 1
    assert chapters[0]["name"] == "海边旅行"
    assert chapters[0]["photo_ids"] == [photo_a["id"], photo_b["id"], photo_c["id"]]

    plan_response = client.post(f"/api/v1/albums/{album['id']}/plan", headers=headers)
    assert plan_response.status_code == 202
    plan_task = plan_response.json()["data"]["task"]
    run_task_worker(plan_task)
    pages_response = client.get(f"/api/v1/albums/{album['id']}/pages", headers=headers)
    pages = pages_response.json()["data"]
    assert len(pages) == 1
    first_page = pages[0]
    assert first_page["template"] == "one_large_two_small"
    assert first_page["photo_ids"] == [photo_c["id"], photo_a["id"], photo_b["id"]]
    assert first_page["meta"]["style_key"] == "warm_family"
    assert first_page["meta"]["title"] == "海边的第一天"

    render_response = client.post(f"/api/v1/albums/{album['id']}/render", headers=headers)
    assert render_response.status_code == 202
    render_task = render_response.json()["data"]["task"]
    run_task_worker(render_task)

    preview_response = client.get(f"/api/v1/albums/{album['id']}/preview", headers=headers)
    assert preview_response.status_code == 200
    preview_html = preview_response.json()["data"]["html"]
    assert "海边的第一天" in preview_html
    assert "风很轻，光很暖" in preview_html
    assert "一家人在海边合影" in preview_html
