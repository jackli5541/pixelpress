from __future__ import annotations

from copy import deepcopy
from math import isclose
from typing import Any


LAYOUT_VERSION = 2
PAGE_NUMBER_BAND = 0.08
MIN_GAP = 0.018
MAX_CENTER_OFFSET = 0.18
MIN_PHOTO_WIDTH = 0.06
MIN_DESCRIPTION_WIDTH = 0.2
MAX_DESCRIPTION_LENGTH = 500


class FreeformLayoutError(ValueError):
    pass


def _aspect(photo: Any) -> float:
    width = float(getattr(photo, "width", None) or (photo.get("width") if isinstance(photo, dict) else 0) or 1)
    height = float(getattr(photo, "height", None) or (photo.get("height") if isinstance(photo, dict) else 0) or 1)
    return max(0.05, min(20.0, width / height))


def _height_for(width: float, aspect_ratio: float, content_ratio: float) -> float:
    return width * content_ratio / aspect_ratio


def description_height(text: str, width: float) -> float:
    if not text.strip():
        return 0.0
    chars_per_line = max(8, int(width * 46))
    lines = max(1, (len(text.strip()) + chars_per_line - 1) // chars_per_line)
    return min(0.24, 0.035 + lines * 0.028)


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


def build_freeform_layout(
    photos: list[Any],
    meta: dict[str, Any] | None = None,
    *,
    page_width_mm: float = 210,
    page_height_mm: float = 297,
    safe_margin_mm: float = 8,
) -> dict[str, Any]:
    source = deepcopy(meta or {})
    if source.get("layout_version") == LAYOUT_VERSION and isinstance(source.get("elements"), list):
        return source

    content_width = max(1.0, page_width_mm - safe_margin_mm * 2)
    content_height = max(1.0, page_height_mm - safe_margin_mm * 2)
    content_ratio = content_width / content_height
    count = max(1, len(photos))
    columns = 1 if count == 1 else 2
    rows = (count + columns - 1) // columns
    available_bottom = 1.0 - PAGE_NUMBER_BAND
    description_text = _legacy_description(source)
    desc_width = 0.64
    desc_height = max(0.06, description_height(description_text, desc_width))
    media_bottom = available_bottom - desc_height - 0.05
    max_cell_width = (0.86 - (columns - 1) * 0.035) / columns
    max_cell_height = (media_bottom - 0.14 - (rows - 1) * 0.035) / rows
    elements: list[dict[str, Any]] = []
    cell_heights: list[float] = []
    for photo in photos:
        aspect = _aspect(photo)
        width = max(MIN_PHOTO_WIDTH, min(max_cell_width, max_cell_height * aspect / content_ratio))
        height = _height_for(width, aspect, content_ratio)
        cell_heights.append(height)
        elements.append({
            "type": "photo",
            "photo_id": str(getattr(photo, "id", None) or photo.get("id")),
            "x": 0.0,
            "y": 0.0,
            "width": round(width, 6),
            "height": round(height, 6),
            "aspect_ratio": round(aspect, 6),
            "order": len(elements),
        })

    grid_height = rows * max_cell_height + max(0, rows - 1) * 0.035
    grid_top = max(0.04, (media_bottom - grid_height) / 2)
    for index, element in enumerate(elements):
        row, column = divmod(index, columns)
        cell_left = 0.07 + column * (max_cell_width + 0.035)
        element["x"] = round(cell_left + (max_cell_width - element["width"]) / 2, 6)
        element["y"] = round(grid_top + row * (max_cell_height + 0.035) + (max_cell_height - element["height"]) / 2, 6)

    description = {
        "text": description_text,
        "x": round((1 - desc_width) / 2, 6),
        "y": round(media_bottom + 0.025, 6),
        "width": desc_width,
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
    if layout.get("layout_version") != LAYOUT_VERSION:
        raise FreeformLayoutError("layout_version must be 2")
    content_ratio = max(1.0, page_width_mm - safe_margin_mm * 2) / max(1.0, page_height_mm - safe_margin_mm * 2)
    elements = layout.get("elements")
    if not isinstance(elements, list):
        raise FreeformLayoutError("elements must be a list")
    expected_ids = set(photos_by_id)
    actual_ids: set[str] = set()
    rects: list[tuple[float, float, float, float]] = []
    for index, item in enumerate(elements):
        if not isinstance(item, dict) or item.get("type") != "photo":
            raise FreeformLayoutError("only photo elements are supported")
        photo_id = str(item.get("photo_id") or "")
        if photo_id not in expected_ids or photo_id in actual_ids:
            raise FreeformLayoutError("layout references an invalid or duplicate photo")
        actual_ids.add(photo_id)
        try:
            x, y, width = (float(item[key]) for key in ("x", "y", "width"))
            height = float(item["height"])
        except (KeyError, TypeError, ValueError) as exc:
            raise FreeformLayoutError("photo geometry is invalid") from exc
        aspect = _aspect(photos_by_id[photo_id])
        expected_height = _height_for(width, aspect, content_ratio)
        if width < MIN_PHOTO_WIDTH or height <= 0 or not isclose(height, expected_height, rel_tol=0.015, abs_tol=0.003):
            raise FreeformLayoutError("photo aspect ratio must be preserved")
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
    except (TypeError, ValueError) as exc:
        raise FreeformLayoutError("description geometry is invalid") from exc
    dh = description_height(text, dw)
    if text:
        if dw < MIN_DESCRIPTION_WIDTH or dx < 0 or dy < 0 or dx + dw > 1.0001 or dy + dh > 1 - PAGE_NUMBER_BAND:
            raise FreeformLayoutError("description is outside the safe content area")
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
    normalized["description"] = {"text": text, "x": dx, "y": dy, "width": dw}
    return normalized
