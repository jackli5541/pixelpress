from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.ai.factory import get_ai_provider
from app.ai.schemas import ChapterNarrativeOutput
from app.ai.types import ImagePayload, ProviderConnectionConfig, ProviderRequest
from app.core.config import get_settings


class ChapterPipelineError(RuntimeError):
    pass


_CALENDAR_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:\d{4}年)?\d{1,2}月\d{1,2}(?:日|号|[-—至到]\d{1,2}日)"
    r"|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    r"|\d{4}年\d{1,2}月"
    r"|\d{4}年"
    r")\s*(?:[·:：,，\-—|]\s*)*"
)


def normalize_chapter_name(name: str, fallback: str) -> str:
    original = name.strip()
    without_calendar = _CALENDAR_PREFIX.sub("", original, count=1).strip(" ·:：,，-—|")
    return without_calendar or fallback.strip() or "未命名章节"


def _rounded_gps(photos: list[dict[str, Any]]) -> list[tuple[float, float]]:
    values: list[tuple[float, float]] = []
    for photo in photos:
        latitude = photo.get("gps_latitude")
        longitude = photo.get("gps_longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            values.append((round(float(latitude), 3), round(float(longitude), 3)))
    return sorted(set(values))[:5]


def _build_user_prompt(chapter: dict[str, Any], photos: list[dict[str, Any]], image_count: int) -> str:
    tags = sorted({str(tag).strip() for photo in photos for tag in (photo.get("scene_tags") or []) if str(tag).strip()})
    photo_by_id = {str(photo.get("id")): photo for photo in photos}
    representative_ids = list((chapter.get("clustering_explanation") or {}).get("representative_photo_ids") or [])
    representatives = [photo_by_id[photo_id] for photo_id in representative_ids if photo_id in photo_by_id][:image_count]
    theme = (chapter.get("clustering_explanation") or {}).get("theme") or {}
    image_mapping = [
        {"image_index": index, "photo_id": str(photo.get("id")), "filename": str(photo.get("filename") or "")}
        for index, photo in enumerate(representatives, 1)
    ]
    return (
        "请为一个已经由确定性算法完成分组的相册章节生成名称和一句摘要。\n"
        "你不能改变照片归属，也不能输出 photo_ids。不要识别或猜测人物身份；"
        "不要仅凭坐标猜测具体地点。\n"
        "名称应优先概括画面内容、活动、地点类型或氛围，简洁、自然、有区分度。"
        "名称中不要写具体年月日，也不要机械复述 time_range；time_range 只用于理解先后顺序和生成摘要。"
        "只有清晨、黄昏、傍晚、夜间等时段确实能区分章节时，名称才可以使用时段词。"
        "证据不足时使用“沿途所见”“旅途片段”一类中性内容名称，不要使用日期作为名称。\n"
        "输出必须是 JSON：{\"chapter_key\": str, \"name\": str, \"description\": str}。\n\n"
        f"chapter_key={chapter['chapter_key']}\n"
        f"time_range={chapter.get('time_range')}\n"
        f"photo_count={len(photos)}\n"
        f"story_theme={theme.get('title', '完整记录')}\n"
        f"chapter_strategy={theme.get('chapter_strategy', 'balanced')}\n"
        f"rounded_gps={_rounded_gps(photos)}\n"
        f"scene_tags={tags[:20]}\n"
        f"representative_image_mapping={image_mapping}\n"
        f"representative_image_count={image_count}\n"
        "附图按代表性顺序排列，均属于这个章节。"
    )


async def name_chapter_with_ai(
    chapter: dict[str, Any],
    photos: list[dict[str, Any]],
    *,
    images: list[ImagePayload],
    provider_connection: ProviderConnectionConfig | None = None,
) -> tuple[ChapterNarrativeOutput, dict[str, Any]]:
    settings = get_settings()
    provider_name = provider_connection.provider if provider_connection else settings.ai_provider_b2
    provider = get_ai_provider(provider_name)
    request = ProviderRequest(
        system_prompt=(
            "你是谨慎的家庭相册编辑。你只负责为已经固定的章节生成名称和摘要，"
            "不得改变章节结构，不得虚构人物身份、地点或事件。"
        ),
        user_prompt=_build_user_prompt(chapter, photos, len(images)),
        output_schema=ChapterNarrativeOutput.model_json_schema(),
        model=provider_connection.model if provider_connection and provider_connection.model else settings.ai_model_b2,
        images=images,
        connection=provider_connection,
    )
    response = await provider.infer_json(request)
    try:
        output = ChapterNarrativeOutput.model_validate(response.payload)
    except ValidationError as exc:  # noqa: BLE001
        raise ChapterPipelineError(f"chapter narrative schema validation failed: {exc}") from exc
    if output.chapter_key != chapter["chapter_key"]:
        raise ChapterPipelineError("chapter narrative returned an unexpected chapter_key")
    output = output.model_copy(update={
        "name": normalize_chapter_name(output.name, str(chapter.get("name") or "")),
    })
    return output, response.debug | {"provider": response.provider, "model": response.model}
