from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import ValidationError

from app.ai.factory import get_ai_provider
from app.ai.schemas import ChapterClusterOutput
from app.ai.types import ProviderConnectionConfig, ProviderRequest
from app.core.config import get_settings


class ChapterPipelineError(RuntimeError):
    pass


def _build_user_prompt(photos: list[dict[str, Any]], baseline: list[dict[str, Any]]) -> str:
    photo_lines: list[str] = []
    for photo in photos:
        tags = ",".join(photo.get("scene_tags") or [])
        photo_lines.append(
            f"- photo_id={photo['id']}; taken_at={photo.get('taken_at')}; uploaded_at={photo.get('uploaded_at')}; "
            f"gps=({photo.get('gps_latitude')},{photo.get('gps_longitude')}); device_model={photo.get('device_model')}; "
            f"quality_score={photo.get('quality_score')}; filename={photo.get('filename')}; tags={tags}"
        )
    baseline_lines = [
        f"- baseline_chapter={item.get('name')}; photo_ids={','.join(item.get('photo_ids', []))}"
        for item in baseline
    ]
    return (
        "请根据以下照片元数据，为一本相册生成章节分组。\n"
        "输出必须是 JSON，字段结构为 {\"chapters\": [{\"name\": str, \"description\": str, \"photo_ids\": [str]}]}。\n"
        "要求：所有照片必须被覆盖且只能出现一次；章节名自然、简洁；描述一句话。\n"
        "优先保证同一事件不拆散，避免不同事件被机械合并。\n\n"
        "照片列表：\n"
        f"{chr(10).join(photo_lines)}\n\n"
        "规则版时间聚类参考：\n"
        f"{chr(10).join(baseline_lines) if baseline_lines else '- 无'}"
    )


async def cluster_photos_with_ai(
    photos: list[dict[str, Any]],
    *,
    baseline: list[dict[str, Any]],
    provider_connection: ProviderConnectionConfig | None = None,
) -> tuple[ChapterClusterOutput, dict[str, Any]]:
    settings = get_settings()
    provider_name = provider_connection.provider if provider_connection else settings.ai_provider_b2
    provider = get_ai_provider(provider_name)
    request = ProviderRequest(
        system_prompt=(
            "你是专业相册编辑。你需要把照片按事件与叙事进行章节聚类，"
            "输出稳定、简洁、可直接用于相册制作的 JSON。"
        ),
        user_prompt=_build_user_prompt(photos, baseline),
        output_schema=ChapterClusterOutput.model_json_schema(),
        model=provider_connection.model if provider_connection and provider_connection.model else settings.ai_model_b2,
        connection=provider_connection,
    )
    response = await provider.infer_json(request)
    try:
        output = ChapterClusterOutput.model_validate(response.payload)
    except ValidationError as exc:  # noqa: BLE001
        raise ChapterPipelineError(f"chapter schema validation failed: {exc}") from exc

    normalized = normalize_chapter_output(output, [photo["id"] for photo in photos])
    return normalized, response.debug | {"provider": response.provider, "model": response.model}


def normalize_chapter_output(output: ChapterClusterOutput, source_photo_ids: list[str]) -> ChapterClusterOutput:
    source_set = set(source_photo_ids)
    seen: Counter[str] = Counter()
    normalized_chapters: list[dict[str, Any]] = []

    for chapter in output.chapters:
        deduped_ids: list[str] = []
        for photo_id in chapter.photo_ids:
            if photo_id in source_set and seen[photo_id] == 0:
                deduped_ids.append(photo_id)
                seen[photo_id] += 1
        if deduped_ids:
            normalized_chapters.append(
                {
                    "name": chapter.name.strip() or "未命名章节",
                    "description": chapter.description.strip(),
                    "photo_ids": deduped_ids,
                }
            )

    missing = [photo_id for photo_id in source_photo_ids if seen[photo_id] == 0]
    for photo_id in missing:
        normalized_chapters.append(
            {
                "name": "补充分组",
                "description": "模型未覆盖，已自动补入",
                "photo_ids": [photo_id],
            }
        )

    return ChapterClusterOutput.model_validate({"chapters": normalized_chapters})
