from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.ai.factory import get_ai_provider
from app.ai.schemas import LayoutRecommendationOutput
from app.ai.types import ProviderConnectionConfig, ProviderRequest
from app.core.config import get_settings
from app.engines.layout_engine.templates import STYLE_PRESETS


class LayoutPipelineError(RuntimeError):
    pass


def _build_user_prompt(
    photos: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    *,
    chapter_name: str,
    chapter_description: str,
    page_role_hint: str,
    style_catalog: dict[str, dict[str, Any]],
    print_spec: dict[str, Any],
) -> str:
    photo_lines = []
    for photo in photos:
        tags = ",".join(photo.get("scene_tags") or [])
        photo_lines.append(
            f"- photo_id={photo['id']}; size={photo.get('width')}x{photo.get('height')}; "
            f"quality={photo.get('quality_score')}; tags={tags}; filename={photo.get('filename')}"
        )
    template_lines = [
        (
            f"- template_key={item['template_key']}; preferred_photo_count={item['preferred_photo_count']}; "
            f"portrait_focus={item['supports_portrait_focus']}; story_style={item['story_style']}; "
            f"description={item['description']}"
        )
        for item in templates
    ]
    style_lines = [
        f"- style_key={key}; background={value['background']}; accent={value['accent_color']}; label={value['label']}"
        for key, value in style_catalog.items()
    ]
    return (
        "请为一本可打印相册生成单页排版决策。\n"
        "输出必须是 JSON，字段结构为 "
        "{\"style_key\": str, \"page_role\": str, \"template_key\": str, \"ordered_photo_ids\": [str], "
        "\"title\": str, \"subtitle\": str, \"captions\": [{\"photo_id\": str, \"text\": str}], "
        "\"confidence\": float, \"reason\": str, \"alternatives\": [str]}。\n"
        "标题、caption 必须简短自然，适合真实印刷页面阅读。\n"
        "同一页面所有照片必须被覆盖，ordered_photo_ids 不能遗漏。\n\n"
        f"章节名：{chapter_name}\n"
        f"章节描述：{chapter_description}\n"
        f"页面角色提示：{page_role_hint}\n"
        f"印刷参数：{print_spec}\n\n"
        "照片列表：\n"
        f"{chr(10).join(photo_lines)}\n\n"
        "模板目录：\n"
        f"{chr(10).join(template_lines)}\n\n"
        "风格目录：\n"
        f"{chr(10).join(style_lines)}"
    )


async def recommend_layout_with_ai(
    photos: list[dict[str, Any]],
    templates: list[dict[str, Any]],
    *,
    chapter_name: str,
    chapter_description: str,
    page_role_hint: str,
    print_spec: dict[str, Any],
    provider_connection: ProviderConnectionConfig | None = None,
) -> tuple[LayoutRecommendationOutput, dict[str, Any]]:
    settings = get_settings()
    provider_name = provider_connection.provider if provider_connection else settings.ai_provider_b3
    provider = get_ai_provider(provider_name)
    request = ProviderRequest(
        system_prompt=(
            "你是专业相册设计师。请在统一视觉系统内为页面生成可打印相册排版方案，"
            "保证结构化输出稳定、简洁、可落地。"
        ),
        user_prompt=_build_user_prompt(
            photos,
            templates,
            chapter_name=chapter_name,
            chapter_description=chapter_description,
            page_role_hint=page_role_hint,
            style_catalog=STYLE_PRESETS,
            print_spec=print_spec,
        ),
        output_schema=LayoutRecommendationOutput.model_json_schema(),
        model=provider_connection.model if provider_connection and provider_connection.model else settings.ai_model_b3,
        connection=provider_connection,
    )
    response = await provider.infer_json(request)
    try:
        output = LayoutRecommendationOutput.model_validate(response.payload)
    except ValidationError as exc:  # noqa: BLE001
        raise LayoutPipelineError(f"layout schema validation failed: {exc}") from exc

    normalized = normalize_layout_output(output, photos, templates)
    return normalized, response.debug | {"provider": response.provider, "model": response.model}


def normalize_layout_output(
    output: LayoutRecommendationOutput,
    source_photos: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> LayoutRecommendationOutput:
    source_ids = [photo["id"] for photo in source_photos]
    source_id_set = set(source_ids)
    template_keys = {item["template_key"] for item in templates}

    ordered_ids = [photo_id for photo_id in output.ordered_photo_ids if photo_id in source_id_set]
    if len(dict.fromkeys(ordered_ids)) != len(source_ids):
        ordered_ids = source_ids[:]
    else:
        ordered_ids = list(dict.fromkeys(ordered_ids))
        missing = [photo_id for photo_id in source_ids if photo_id not in ordered_ids]
        ordered_ids.extend(missing)

    captions = []
    seen_caption_ids: set[str] = set()
    for item in output.captions:
        if item.photo_id in source_id_set and item.photo_id not in seen_caption_ids:
            captions.append({"photo_id": item.photo_id, "text": item.text.strip()[:120]})
            seen_caption_ids.add(item.photo_id)
    for photo_id in ordered_ids:
        if photo_id not in seen_caption_ids:
            captions.append({"photo_id": photo_id, "text": ""})

    payload = {
        "style_key": output.style_key if output.style_key in STYLE_PRESETS else "warm_family",
        "page_role": output.page_role,
        "template_key": output.template_key if output.template_key in template_keys else templates[0]["template_key"],
        "ordered_photo_ids": ordered_ids,
        "title": output.title.strip()[:80],
        "subtitle": output.subtitle.strip()[:120],
        "captions": captions,
        "confidence": output.confidence,
        "reason": output.reason.strip()[:240],
        "alternatives": [item for item in output.alternatives if item in template_keys][:2],
    }
    return LayoutRecommendationOutput.model_validate(payload)
