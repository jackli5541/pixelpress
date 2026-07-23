from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt
from typing import Any


PLANNING_VERSION = "spread-v4-complete-photo-fit-v1"
MIN_SLOT_SHORT_EDGE_MM = 45.0
MIN_SLOT_AREA_MM2 = 2400.0
MAX_HERO_CROP_AREA = 0.10
MAX_HERO_EDGE_CROP = 0.12


@dataclass(frozen=True)
class SpreadRecipe:
    key: str
    label: str
    photo_count: int
    description: str
    left_slots: tuple[str, ...]
    right_slots: tuple[str, ...]
    left_template: str
    right_template: str
    text_side: str


@dataclass(frozen=True)
class SlotGeometry:
    """Approximate printable photo area for a template slot on a 10-inch page."""

    width_mm: float
    height_mm: float

    @property
    def aspect_ratio(self) -> float:
        return self.width_mm / self.height_mm

    @property
    def is_printable(self) -> bool:
        return (
            min(self.width_mm, self.height_mm) >= MIN_SLOT_SHORT_EDGE_MM
            and self.width_mm * self.height_mm >= MIN_SLOT_AREA_MM2
        )


# These are the printable media areas after the 8 mm safety margin, panel
# padding and grid gaps. Keeping them in the planner makes candidate selection
# use the same physical constraints as PDF rendering.
TEMPLATE_SLOT_GEOMETRIES: dict[str, tuple[SlotGeometry, ...]] = {
    "spread_text": (),
    "full_page": (SlotGeometry(222, 222),),
    "cinema_landscape": (SlotGeometry(222, 148),),
    "gallery_portrait": (SlotGeometry(110, 222),),
    "half_half": (SlotGeometry(222, 106), SlotGeometry(222, 106)),
    "two_column": (SlotGeometry(106, 222), SlotGeometry(106, 222)),
    "staggered_duo": (SlotGeometry(122, 206), SlotGeometry(90, 176)),
    "grid_3": (SlotGeometry(222, 104), SlotGeometry(106, 94), SlotGeometry(106, 94)),
    "grid_4": (SlotGeometry(106, 106),) * 4,
    "grid_5": (
        SlotGeometry(106, 142),
        SlotGeometry(92, 68),
        SlotGeometry(92, 68),
        SlotGeometry(92, 68),
        SlotGeometry(222, 68),
    ),
    "one_large_two_small": (SlotGeometry(126, 222), SlotGeometry(86, 106), SlotGeometry(86, 106)),
    "triptych_strip": (SlotGeometry(70, 222),) * 3,
    "mosaic_mix": (SlotGeometry(122, 68), SlotGeometry(92, 68), SlotGeometry(92, 68), SlotGeometry(222, 68)),
}


SPREAD_RECIPES: tuple[SpreadRecipe, ...] = (
    SpreadRecipe("single_story", "单图图文", 1, "左页短文，右页单张主视觉。", (), ("right_hero",), "spread_text", "gallery_portrait", "left"),
    SpreadRecipe("single_gallery", "单图留白", 1, "单张照片以画廊式留白呈现。", ("left_hero",), (), "gallery_portrait", "spread_text", "right"),
    SpreadRecipe("single_cinema", "单图横幅", 1, "横向主图配下方短文。", ("left_hero",), (), "cinema_landscape", "spread_text", "right"),
    SpreadRecipe("facing_duo", "双页对照", 2, "左右各一张主图。", ("left_hero",), ("right_hero",), "full_page", "full_page", "none"),
    SpreadRecipe("text_duo", "双图图文", 2, "两张照片与短文形成留白节奏。", ("left_hero",), ("right_support",), "gallery_portrait", "gallery_portrait", "right"),
    SpreadRecipe("asym_duo", "双图错落", 2, "横竖图以不对称画幅拼接。", ("left_hero",), ("right_detail",), "cinema_landscape", "gallery_portrait", "left"),
    SpreadRecipe("three_story", "三图故事", 3, "左页主图，右页两张连续镜头。", ("left_hero",), ("right_top", "right_bottom"), "full_page", "half_half", "left"),
    SpreadRecipe("three_triptych", "三联画", 3, "三张照片按时间连续排列。", ("left_a", "left_b", "left_c"), (), "triptych_strip", "spread_text", "right"),
    SpreadRecipe("three_collage", "三图拼贴", 3, "两张细节衬托一张主视觉。", ("left_top", "left_bottom"), ("right_hero",), "half_half", "full_page", "right"),
    SpreadRecipe("hero_three", "一大三小", 4, "左页三张细节，右页一张主视觉。", ("left_top", "left_middle", "left_bottom"), ("right_hero",), "grid_3", "full_page", "right"),
    SpreadRecipe("four_grid", "四图方格", 4, "两页各两张，结构均衡。", ("left_a", "left_b"), ("right_a", "right_b"), "two_column", "two_column", "none"),
    SpreadRecipe("four_mosaic", "四图杂志", 4, "四图拼贴并保留说明区。", ("left_a", "left_b", "left_c", "left_d"), (), "mosaic_mix", "spread_text", "right"),
    SpreadRecipe("two_plus_three", "双图加三图", 5, "左页两张、右页三张的完整事件组。", ("left_top", "left_bottom"), ("right_top", "right_middle", "right_bottom"), "half_half", "grid_3", "none"),
    SpreadRecipe("five_mosaic", "五图层次", 5, "四张细节衬托一张主图。", ("left_a", "left_b", "left_c", "left_d"), ("right_hero",), "grid_4", "full_page", "right"),
    SpreadRecipe("six_sequence", "六图序列", 6, "左右各三张，适合连续过程。", ("left_top", "left_middle", "left_bottom"), ("right_top", "right_middle", "right_bottom"), "grid_3", "grid_3", "none"),
    SpreadRecipe("six_contact", "六图联系表", 6, "四张环境与两张细节形成节奏。", ("left_a", "left_b", "left_c", "left_d"), ("right_a", "right_b"), "grid_4", "half_half", "left"),
    SpreadRecipe("nine_grid", "九宫格", 9, "九张照片以联系表方式保留完整事件。", ("left_1", "left_2", "left_3", "left_4"), ("right_1", "right_2", "right_3", "right_4", "right_5"), "grid_4", "grid_5", "right"),
)

BOOK_STYLES: dict[str, dict[str, str]] = {
    "minimal_white": {
        "label": "极简留白",
        "description": "参考样册的纯白纸张、克制字阶和大面积留白。",
        "background": "#ffffff",
        "primary_color": "#171717",
        "secondary_color": "#666666",
        "accent_color": "#171717",
        "heading_font": "'Noto Serif CJK SC', 'Noto Serif SC', serif",
        "body_font": "'Noto Sans CJK SC', 'Noto Sans SC', sans-serif",
    },
    "editorial_journal": {
        "label": "编辑纪实",
        "description": "更鲜明的标题和细线框架，适合旅行与城市记录。",
        "background": "#fbfbfa",
        "primary_color": "#111111",
        "secondary_color": "#555555",
        "accent_color": "#9f2f25",
        "heading_font": "'Noto Serif CJK SC', 'Noto Serif SC', serif",
        "body_font": "'Noto Sans CJK SC', 'Noto Sans SC', sans-serif",
    },
    "warm_memory": {
        "label": "温暖记忆",
        "description": "柔和纸色和安静的暖色强调，适合家庭与成长记录。",
        "background": "#fffaf2",
        "primary_color": "#2f2924",
        "secondary_color": "#74685f",
        "accent_color": "#a65f43",
        "heading_font": "'Noto Serif CJK SC', 'Noto Serif SC', serif",
        "body_font": "'Noto Sans CJK SC', 'Noto Sans SC', sans-serif",
    },
}

LEGACY_STYLE_ALIASES = {
    "minimal": "minimal_white",
    "editorial": "editorial_journal",
    "warm_family": "warm_memory",
    "playful_child": "warm_memory",
}


def layout_catalog() -> dict[str, Any]:
    return {
        "planning_version": PLANNING_VERSION,
        "candidate_count": 3,
        "styles": [{"key": key, **value} for key, value in BOOK_STYLES.items()],
        "recipes": [
            {
                "key": recipe.key,
                "label": recipe.label,
                "photo_count": recipe.photo_count,
                "description": recipe.description,
                "text_side": recipe.text_side,
            }
            for recipe in SPREAD_RECIPES
        ],
    }


def normalize_style_key(value: str | None) -> str:
    candidate = LEGACY_STYLE_ALIASES.get(str(value or ""), str(value or ""))
    return candidate if candidate in BOOK_STYLES else "minimal_white"


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def _recipe_counts(photo_count: int) -> list[int]:
    if photo_count <= 0:
        return []
    # Dense contact sheets are valid when they preserve each frame. Candidate
    # selection handles aspect-ratio suitability; group sizing stays varied.
    preferences = {9: 0.35, 6: 0.9, 5: 0.2, 4: 0.35, 3: 0.8, 2: 1.5, 1: 2.8}
    best: list[tuple[float, list[int]] | None] = [None] * (photo_count + 1)
    best[0] = (0.0, [])
    for total in range(1, photo_count + 1):
        candidates: list[tuple[float, list[int]]] = []
        for size in (1, 2, 3, 4, 5, 6, 9):
            previous = total - size
            if previous < 0 or best[previous] is None:
                continue
            previous_cost, sequence = best[previous]
            repeat_penalty = 0.35 if sequence and sequence[-1] == size else 0.0
            candidates.append((previous_cost + 10.0 + preferences[size] + repeat_penalty, [*sequence, size]))
        best[total] = min(candidates, key=lambda item: (item[0], len(item[1]), item[1]))
    return best[photo_count][1] if best[photo_count] else []


def _embedding_signature(feature: dict[str, Any] | None) -> tuple[str, str, int] | None:
    if not feature or not feature.get("embedding"):
        return None
    return (
        str(feature.get("embedding_provider") or ""),
        str(feature.get("embedding_model") or ""),
        int(feature.get("embedding_dimension") or 0),
    )


def embeddings_compatible(photos: list[dict[str, Any]], features: dict[str, dict[str, Any]]) -> bool:
    signatures = {_embedding_signature(features.get(str(photo["id"]))) for photo in photos}
    signatures.discard(None)
    return len(signatures) == 1 and len(features) >= len(photos) and all(
        _embedding_signature(features.get(str(photo["id"]))) is not None for photo in photos
    )


def _cosine_distance(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 1.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = sqrt(sum(float(value) ** 2 for value in left))
    right_norm = sqrt(sum(float(value) ** 2 for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 1.0
    return 1.0 - max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _ordered_photos(photos: list[dict[str, Any]], features: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    latest = datetime.max.replace(tzinfo=UTC)
    indexed = list(enumerate(photos))
    indexed.sort(key=lambda item: (_parse_time(item[1].get("taken_at")) or latest, item[0], str(item[1]["id"])))
    ordered = [item for _, item in indexed]
    compatible = embeddings_compatible(ordered, features)
    if not compatible or len(ordered) < 3:
        return ordered, compatible

    remaining = ordered[:]
    coherent: list[dict[str, Any]] = [remaining.pop(0)]
    while remaining:
        anchor = coherent[-1]
        anchor_embedding = features[str(anchor["id"])]["embedding"]
        window = remaining[: min(8, len(remaining))]
        selected = min(
            window,
            key=lambda item: (
                _cosine_distance(anchor_embedding, features[str(item["id"])]["embedding"]),
                _parse_time(item.get("taken_at")) or latest,
                str(item["id"]),
            ),
        )
        coherent.append(selected)
        remaining.remove(selected)
    return coherent, True


def _photo_score(photo: dict[str, Any]) -> float:
    quality = float(photo.get("quality_score") or 0.0)
    pixels = float(photo.get("width") or 0) * float(photo.get("height") or 0)
    return quality * 100.0 + min(pixels / 1_000_000.0, 30.0)


def _focal_point(photo: dict[str, Any]) -> tuple[float, float]:
    faces = ((photo.get("cleaning_features") or {}).get("faces") or {}).get("items") or []
    boxes = [item.get("bbox") for item in faces if isinstance(item, dict) and len(item.get("bbox") or []) == 4]
    if not boxes:
        return 0.5, 0.5
    left = min(float(box[0]) for box in boxes)
    top = min(float(box[1]) for box in boxes)
    right = max(float(box[0]) + float(box[2]) for box in boxes)
    bottom = max(float(box[1]) + float(box[3]) for box in boxes)
    return round(max(0.0, min(1.0, (left + right) / 2)), 4), round(max(0.0, min(1.0, (top + bottom) / 2)), 4)


def _photo_aspect_ratio(photo: dict[str, Any]) -> float:
    width = float(photo.get("width") or 0)
    height = float(photo.get("height") or 0)
    return width / height if width > 0 and height > 0 else 1.0


def _crop_metrics(photo_aspect: float, slot_aspect: float) -> tuple[float, float]:
    """Return cropped source area and the largest crop on either source edge."""

    if photo_aspect <= 0 or slot_aspect <= 0:
        return 1.0, 1.0
    retained_fraction = max(0.0, min(1.0, min(photo_aspect / slot_aspect, slot_aspect / photo_aspect)))
    crop = 1.0 - retained_fraction
    return crop, crop


def _slot_fit_score(photo: dict[str, Any], geometry: SlotGeometry) -> float:
    if not geometry.is_printable:
        return -100.0
    photo_aspect = _photo_aspect_ratio(photo)
    aspect_fit = min(photo_aspect / geometry.aspect_ratio, geometry.aspect_ratio / photo_aspect)
    return max(0.0, aspect_fit) * 12.0 + _photo_score(photo) / 100.0


def _recipe_slot_geometries(recipe: SpreadRecipe) -> list[tuple[str, str, SlotGeometry]]:
    result: list[tuple[str, str, SlotGeometry]] = []
    for side, slot_keys, template in (
        ("left", recipe.left_slots, recipe.left_template),
        ("right", recipe.right_slots, recipe.right_template),
    ):
        geometries = TEMPLATE_SLOT_GEOMETRIES.get(template, ())
        for index, slot_key in enumerate(slot_keys):
            geometry = geometries[index] if index < len(geometries) else SlotGeometry(45, 54)
            result.append((side, slot_key, geometry))
    return result


def _photo_slot_presentation(photo: dict[str, Any], slot_key: str, geometry: SlotGeometry) -> dict[str, Any]:
    crop_area, edge_crop = _crop_metrics(_photo_aspect_ratio(photo), geometry.aspect_ratio)
    allow_cover = (
        "hero" in slot_key
        and crop_area <= MAX_HERO_CROP_AREA
        and edge_crop <= MAX_HERO_EDGE_CROP
    )
    return {
        "fit_mode": "cover" if allow_cover else "contain",
        "crop_area": round(crop_area, 4),
        "crop_edge": round(edge_crop, 4),
        "slot_width_mm": geometry.width_mm,
        "slot_height_mm": geometry.height_mm,
    }


def _recipe_fit_penalty(recipe: SpreadRecipe, photos: list[dict[str, Any]]) -> float:
    geometries = _recipe_slot_geometries(recipe)
    if len(geometries) != len(photos) or not all(geometry.is_printable for _, _, geometry in geometries):
        return 100.0
    remaining = list(photos)
    penalty = 0.0
    for _, slot_key, geometry in sorted(geometries, key=lambda item: "hero" not in item[1]):
        selected = max(remaining, key=lambda photo: _slot_fit_score(photo, geometry))
        remaining.remove(selected)
        fit = _slot_fit_score(selected, geometry)
        penalty += max(0.0, 8.0 - fit)
        if "hero" not in slot_key and fit < 3.0:
            penalty += 8.0
    return penalty


def _recipe_score(recipe: SpreadRecipe, photos: list[dict[str, Any]], previous_key: str | None) -> tuple[float, str]:
    portrait = sum((photo.get("height") or 0) > (photo.get("width") or 0) * 1.12 for photo in photos)
    landscape = sum((photo.get("width") or 0) > (photo.get("height") or 0) * 1.12 for photo in photos)
    score = _recipe_fit_penalty(recipe, photos)
    if recipe.left_template == "cinema_landscape" or recipe.right_template == "cinema_landscape":
        score -= landscape * 1.2
    if recipe.left_template == "gallery_portrait" or recipe.right_template == "gallery_portrait":
        score -= portrait * 0.9
    if recipe.text_side != "none":
        score -= 0.25
    quality_scores = sorted((_photo_score(photo) for photo in photos), reverse=True)
    if quality_scores and any("hero" in slot for slot in (*recipe.left_slots, *recipe.right_slots)):
        # Hero-oriented recipes are useful only when one frame is meaningfully stronger.
        score -= min(quality_scores[0] - quality_scores[-1], 35.0) / 18.0
    timestamps = sorted(time for time in (_parse_time(photo.get("taken_at")) for photo in photos) if time is not None)
    if len(timestamps) > 1:
        span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        continuity = 1.0 / (1.0 + min(span_hours, 48.0))
        if recipe.key in {"three_triptych", "six_sequence", "nine_grid"}:
            score -= continuity * 1.2
    previous = next((item for item in SPREAD_RECIPES if item.key == previous_key), None)
    if previous is not None:
        if previous.key == recipe.key:
            score += 8.0
        elif (previous.left_template, previous.right_template) == (recipe.left_template, recipe.right_template):
            score += 2.0
    return score, recipe.key


def candidate_recipes(photos: list[dict[str, Any]], previous_key: str | None = None) -> list[SpreadRecipe]:
    options = [recipe for recipe in SPREAD_RECIPES if recipe.photo_count == len(photos)]
    return sorted(options, key=lambda recipe: _recipe_score(recipe, photos, previous_key))[:3]


def get_recipe(recipe_key: str) -> SpreadRecipe | None:
    return next((recipe for recipe in SPREAD_RECIPES if recipe.key == recipe_key), None)


def assign_recipe_slots(group: list[dict[str, Any]], recipe: SpreadRecipe) -> dict[str, list[dict[str, Any]]]:
    slots = _recipe_slot_geometries(recipe)
    remaining = list(group)
    result: dict[str, list[dict[str, Any]]] = {"left": [], "right": []}
    assignments: list[tuple[dict[str, Any], str, str, SlotGeometry]] = []
    # Choose the strongest aspect-ratio match first for hero slots, then fill
    # supporting slots. This avoids using a portrait as a thin landscape tile.
    for side, slot_key, geometry in sorted(slots, key=lambda item: "hero" not in item[1]):
        photo = max(remaining, key=lambda item: _slot_fit_score(item, geometry))
        remaining.remove(photo)
        assignments.append((photo, side, slot_key, geometry))
    left_positions = {slot_key: index for index, slot_key in enumerate(recipe.left_slots)}
    right_positions = {slot_key: index for index, slot_key in enumerate(recipe.right_slots)}
    for photo, side, slot_key, geometry in sorted(
        assignments,
        key=lambda item: (0 if item[1] == "left" else 1, (left_positions if item[1] == "left" else right_positions)[item[2]]),
    ):
        focal_x, focal_y = _focal_point(photo)
        result[side].append(
            {
                "photo_id": str(photo["id"]),
                "slot_key": slot_key,
                "focal_x": focal_x,
                "focal_y": focal_y,
                **_photo_slot_presentation(photo, slot_key, geometry),
            }
        )
    return result


def plan_spreads(
    photos: list[dict[str, Any]],
    *,
    features: dict[str, dict[str, Any]] | None = None,
    chapter_name: str = "",
    chapter_description: str = "",
    start_number: int = 1,
) -> list[dict[str, Any]]:
    if not photos:
        return []
    features = features or {}
    ordered, compatible = _ordered_photos(photos, features)
    counts = _recipe_counts(len(ordered))
    plans: list[dict[str, Any]] = []
    offset = 0
    previous_recipe_key: str | None = None
    for index, count in enumerate(counts):
        group = ordered[offset:offset + count]
        offset += count
        candidates = candidate_recipes(group, previous_recipe_key)
        recipe = candidates[0]
        previous_recipe_key = recipe.key
        assignments = assign_recipe_slots(group, recipe)
        plans.append(
            {
                "spread_number": start_number + index,
                "recipe_key": recipe.key,
                "headline": chapter_name[:18] if index == 0 else "",
                "body": chapter_description[:70] if index == 0 else "",
                "needs_review": not compatible,
                "planning_version": PLANNING_VERSION,
                "meta": {
                    "embedding_mode": "compatible" if compatible else "chronological_fallback",
                    "photo_count": count,
                    "text_side": recipe.text_side,
                    "candidate_recipe_keys": [item.key for item in candidates],
                    "candidate_rank": 0,
                },
                "pages": [
                    {"side": "left", "template": recipe.left_template, "photo_slots": assignments["left"]},
                    {"side": "right", "template": recipe.right_template, "photo_slots": assignments["right"]},
                ],
            }
        )
    return plans


__all__ = [
    "BOOK_STYLES",
    "LEGACY_STYLE_ALIASES",
    "PLANNING_VERSION",
    "SPREAD_RECIPES",
    "assign_recipe_slots",
    "candidate_recipes",
    "embeddings_compatible",
    "get_recipe",
    "layout_catalog",
    "normalize_style_key",
    "plan_spreads",
]
