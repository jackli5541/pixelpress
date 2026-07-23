from __future__ import annotations

from typing import Any

from app.ai.factory import get_ai_provider
from app.ai.types import ImagePayload, ProviderConnectionConfig, ProviderRequest


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["spreads"],
        "properties": {
            "spreads": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["spread_number", "headline", "body"],
                    "properties": {
                        "spread_number": {"type": "integer"},
                        "headline": {"type": "string", "maxLength": 18},
                        "body": {"type": "string", "maxLength": 70},
                        "captions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["photo_id", "text"],
                                "properties": {
                                    "photo_id": {"type": "string"},
                                    "text": {"type": "string", "maxLength": 30},
                                },
                            },
                        },
                    },
                },
            }
        },
    }


async def generate_chapter_spread_copy(
    plans: list[dict[str, Any]],
    photos_by_id: dict[str, dict[str, Any]],
    *,
    chapter_name: str,
    chapter_description: str,
    provider_connection: ProviderConnectionConfig,
    visual_evidence: list[ImagePayload] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for plan in plans:
        photo_ids = [
            slot["photo_id"]
            for page in plan["pages"]
            for slot in page["photo_slots"]
        ]
        evidence.append(
            {
                "spread_number": plan["spread_number"],
                "photo_evidence": [
                    {
                        "photo_id": photo_id,
                        "caption": photos_by_id.get(photo_id, {}).get("custom_caption") or "",
                        "taken_at": str(photos_by_id.get(photo_id, {}).get("taken_at") or ""),
                    }
                    for photo_id in photo_ids
                ],
            }
        )
    provider = get_ai_provider(provider_connection.provider)
    response = await provider.infer_json(
        ProviderRequest(
            system_prompt=(
                "Write restrained photo-book copy in the same language as the chapter. "
                "Use only the supplied chapter description, user captions, timestamps, and visual evidence. "
                "Never invent people, locations, relationships, or events. Return JSON only."
            ),
            user_prompt=(
                f"Chapter: {chapter_name}\nDescription: {chapter_description}\n"
                f"Spreads: {evidence}\n"
                "When contact sheets are attached, they are ordered by spread_number and are visual evidence only. "
                "Headline maximum: 18 Han characters. Body maximum: 70 Han characters. "
                "Captions are optional and should be omitted unless evidence supports them."
            ),
            output_schema=_schema(),
            model=provider_connection.model,
            connection=provider_connection,
            images=visual_evidence or [],
        )
    )
    returned = response.payload.get("spreads") if isinstance(response.payload, dict) else None
    by_number = {
        int(item.get("spread_number")): item
        for item in (returned or [])
        if isinstance(item, dict) and str(item.get("spread_number", "")).isdigit()
    }
    normalized: list[dict[str, Any]] = []
    for plan in plans:
        item = by_number.get(int(plan["spread_number"]), {})
        normalized.append(
            {
                "spread_number": plan["spread_number"],
                "headline": str(item.get("headline") or plan["headline"]).strip()[:18],
                "body": str(item.get("body") or plan["body"]).strip()[:70],
                "captions": [
                    {
                        "photo_id": str(caption.get("photo_id")),
                        "text": str(caption.get("text") or "").strip()[:30],
                    }
                    for caption in (item.get("captions") or [])
                    if isinstance(caption, dict) and caption.get("photo_id")
                ],
            }
        )
    return normalized, response.debug | {
        "provider": response.provider,
        "model": response.model,
        "visual_evidence_count": len(visual_evidence or []),
    }


__all__ = ["generate_chapter_spread_copy"]
