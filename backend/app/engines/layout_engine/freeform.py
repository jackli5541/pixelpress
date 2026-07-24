from __future__ import annotations

from copy import deepcopy
from typing import Any


LAYOUT_VERSION = 3
PAGE_NUMBER_BAND = 0.08
MIN_GAP = 0.018
MAX_CENTER_OFFSET = 0.18
MIN_PHOTO_WIDTH = 0.06
MIN_PHOTO_HEIGHT = 0.05
MIN_DESCRIPTION_WIDTH = 0.2
MIN_DESCRIPTION_HEIGHT = 0.06
MAX_DESCRIPTION_LENGTH = 500
MAX_CROP_FRACTION = 0.15


class FreeformLayoutError(ValueError):
    pass


def _aspect(photo: Any) -> float:
    width = float(getattr(photo, "width", None) or (photo.get("width") if isinstance(photo, dict) else 0) or 1)
    height = float(getattr(photo, "height", None) or (photo.get("height") if isinstance(photo, dict) else 0) or 1)
    return max(0.05, min(20.0, width / height))


def description_height(text: str, width: float) -> float:
    if not text.strip():
        return MIN_DESCRIPTION_HEIGHT
    chars_per_line = max(8, int(width * 46))
    lines = max(1, (len(text.strip()) + chars_per_line - 1) // chars_per_line)
    return max(MIN_DESCRIPTION_HEIGHT, min(0.24, 0.035 + lines * 0.028))


def _legacy_description(meta: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in (meta.get("title"), meta.get("subtitle")):
        text = str(value or "").strip()
        if text and text not in parts:
            parts.append(text)
    captions = [
        str(item.get("text") or "").strip()
        for item in meta.get("captions", [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    parts.extend(text for text in captions if text not in parts)
    return "\n".join(parts)[:MAX_DESCRIPTION_LENGTH]


def _template_slots(template: str, *, top: float, bottom: float) -> list[tuple[float, float, float, float]]:
    left, right, gap = 0.025, 0.975, 0.022
    width = right - left
    height = bottom - top
    half_width = (width - gap) / 2
    half_height = (height - gap) / 2
    if template == "half_half":
        return [(left, top, width, half_height), (left, top + half_height + gap, width, half_height)]
    if template == "two_column":
        return [(left, top, half_width, height), (left + half_width + gap, top, half_width, height)]
    if template == "one_large_two_small":
        large_width = width * 0.62
        small_width = width - large_width - gap
        return [
            (left, top, large_width, height),
            (left + large_width + gap, top, small_width, half_height),
            (left + large_width + gap, top + half_height + gap, small_width, half_height),
        ]
    if template == "grid_3":
        return [
            (left, top, half_width, half_height),
            (left + half_width + gap, top, half_width, half_height),
            (left, top + half_height + gap, width, half_height),
        ]
    if template == "grid_4":
        return [
            (left, top, half_width, half_height),
            (left + half_width + gap, top, half_width, half_height),
            (left, top + half_height + gap, half_width, half_height),
            (left + half_width + gap, top + half_height + gap, half_width, half_height),
        ]
    return [(left, top, width, height)]


def _cover_retained_fraction(image_aspect: float, frame_aspect: float) -> float:
    if image_aspect <= 0 or frame_aspect <= 0:
        return 0.0
    return min(image_aspect / frame_aspect, frame_aspect / image_aspect)


def _upgrade_layout(source: dict[str, Any]) -> dict[str, Any]:
    upgraded = deepcopy(source)
    description = upgraded.get("description") or {}
    width = float(description.get("width", 0.64))
    description["height"] = max(
        float(description.get("height") or 0),
        description_height(str(description.get("text") or ""), width),
    )
    upgraded["description"] = description
    for element in upgraded.get("elements", []):
        element.setdefault("fit", "contain")
    upgraded["layout_version"] = LAYOUT_VERSION
    return upgraded


def build_freeform_layout(
    photos: list[Any],
    meta: dict[str, Any] | None = None,
    *,
    page_width_mm: float = 210,
    page_height_mm: float = 297,
    safe_margin_mm: float = 8,
    template: str = "grid_3",
) -> dict[str, Any]:
    source = deepcopy(meta or {})
    if source.get("layout_version") == LAYOUT_VERSION and isinstance(source.get("elements"), list):
        return source
    if source.get("layout_version") == 2 and isinstance(source.get("elements"), list):
        return _upgrade_layout(source)

    content_width = max(1.0, page_width_mm - safe_margin_mm * 2)
    content_height = max(1.0, page_height_mm - safe_margin_mm * 2)
    content_ratio = content_width / content_height
    available_bottom = 1.0 - PAGE_NUMBER_BAND
    description_text = _legacy_description(source)
    desc_width = 0.64
    desc_height = description_height(description_text, desc_width)
    media_bottom = available_bottom - desc_height - 0.025
    slots = _template_slots(template, top=0.025, bottom=media_bottom)
    if len(slots) != len(photos):
        fallback = {1: "full_page", 2: "two_column", 3: "grid_3", 4: "grid_4"}.get(len(photos), "grid_4")
        slots = _template_slots(fallback, top=0.025, bottom=media_bottom)

    elements: list[dict[str, Any]] = []
    for index, photo in enumerate(photos):
        aspect = _aspect(photo)
        x, y, width, height = slots[min(index, len(slots) - 1)]
        frame_aspect = width * content_ratio / height
        fit = "cover" if _cover_retained_fraction(aspect, frame_aspect) >= 1 - MAX_CROP_FRACTION else "contain"
        elements.append(
            {
                "type": "photo",
                "photo_id": str(getattr(photo, "id", None) or photo.get("id")),
                "x": round(x, 6),
                "y": round(y, 6),
                "width": round(width, 6),
                "height": round(height, 6),
                "aspect_ratio": round(aspect, 6),
                "fit": fit,
                "order": index,
            }
        )

    description = {
        "text": description_text,
        "x": round((1 - desc_width) / 2, 6),
        "y": round(media_bottom + MIN_GAP + 0.004, 6),
        "width": desc_width,
        "height": desc_height,
    }
    source.update({"layout_version": LAYOUT_VERSION, "description": description, "elements": elements})
    return source


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + MIN_GAP and ax + aw + MIN_GAP > bx and ay < by + bh + MIN_GAP and ay + ah + MIN_GAP > by


def validate_freeform_layout(
    layout: dict[str, Any],
    photos_by_id: dict[str, Any],
    *,
    page_width_mm: float = 210,
    page_height_mm: float = 297,
    safe_margin_mm: float = 8,
) -> dict[str, Any]:
    del page_width_mm, page_height_mm, safe_margin_mm
    if layout.get("layout_version") == 2:
        layout = _upgrade_layout(layout)
    if layout.get("layout_version") != LAYOUT_VERSION:
        raise FreeformLayoutError(f"layout_version must be {LAYOUT_VERSION}")
    elements = layout.get("elements")
    if not isinstance(elements, list):
        raise FreeformLayoutError("elements must be a list")
    expected_ids = set(photos_by_id)
    actual_ids: set[str] = set()
    rects: list[tuple[float, float, float, float]] = []
    for item in elements:
        if not isinstance(item, dict) or item.get("type") != "photo":
            raise FreeformLayoutError("only photo elements are supported")
        photo_id = str(item.get("photo_id") or "")
        if photo_id not in expected_ids or photo_id in actual_ids:
            raise FreeformLayoutError("layout references an invalid or duplicate photo")
        actual_ids.add(photo_id)
        try:
            x, y, width, height = (float(item[key]) for key in ("x", "y", "width", "height"))
        except (KeyError, TypeError, ValueError) as exc:
            raise FreeformLayoutError("photo geometry is invalid") from exc
        fit = str(item.get("fit") or "contain")
        if fit not in {"cover", "contain"}:
            raise FreeformLayoutError("photo fit is invalid")
        if width < MIN_PHOTO_WIDTH or height < MIN_PHOTO_HEIGHT:
            raise FreeformLayoutError("photo size is invalid")
        if x < 0 or y < 0 or x + width > 1.0001 or y + height > 1 - PAGE_NUMBER_BAND:
            raise FreeformLayoutError("photo is outside the safe content area")
        rect = (x, y, width, height)
        if any(_rects_overlap(rect, other) for other in rects):
            raise FreeformLayoutError("layout elements overlap")
        rects.append(rect)

    if actual_ids != expected_ids:
        raise FreeformLayoutError("layout must contain every page photo")
    description = layout.get("description") or {}
    text = str(description.get("text") or "")[:MAX_DESCRIPTION_LENGTH]
    try:
        dx, dy, dw = (float(description.get(key, 0)) for key in ("x", "y", "width"))
        dh = float(description.get("height", description_height(text, dw)))
    except (TypeError, ValueError) as exc:
        raise FreeformLayoutError("description geometry is invalid") from exc
    minimum_height = description_height(text, dw)
    if dw < MIN_DESCRIPTION_WIDTH or dh < minimum_height or dx < 0 or dy < 0 or dx + dw > 1.0001 or dy + dh > 1 - PAGE_NUMBER_BAND:
        raise FreeformLayoutError("description is outside the safe content area or too small for its text")
    if text:
        desc_rect = (dx, dy, dw, dh)
        if any(_rects_overlap(desc_rect, other) for other in rects):
            raise FreeformLayoutError("description overlaps a photo")
        rects.append(desc_rect)

    if rects:
        left = min(rect[0] for rect in rects)
        right = max(rect[0] + rect[2] for rect in rects)
        top = min(rect[1] for rect in rects)
        bottom = max(rect[1] + rect[3] for rect in rects)
        if abs((left + right) / 2 - 0.5) > MAX_CENTER_OFFSET or abs((top + bottom) / 2 - (1 - PAGE_NUMBER_BAND) / 2) > MAX_CENTER_OFFSET:
            raise FreeformLayoutError("content group is too far from the visual center")
    normalized = deepcopy(layout)
    normalized["description"] = {"text": text, "x": dx, "y": dy, "width": dw, "height": dh}
    return normalized
