from __future__ import annotations

from app.engines.export_engine.service import normalize_print_spec
from app.engines.layout_engine.service import generate_layout_html
from app.engines.layout_engine.spread_planner import (
    MIN_SLOT_AREA_MM2,
    MIN_SLOT_SHORT_EDGE_MM,
    TEMPLATE_SLOT_GEOMETRIES,
    assign_recipe_slots,
    candidate_recipes,
    get_recipe,
    plan_spreads,
)
from app.engines.layout_engine.templates import STYLE_PRESETS


def _photos(count: int) -> list[dict]:
    return [
        {
            "id": f"photo-{index:03d}",
            "width": 3000 + index,
            "height": 2400,
            "quality_score": 0.7,
            "taken_at": f"2026-01-{(index % 28) + 1:02d}T10:00:00+08:00",
        }
        for index in range(count)
    ]


def _assigned_ids(plans: list[dict]) -> list[str]:
    return [
        slot["photo_id"]
        for spread in plans
        for page in spread["pages"]
        for slot in page["photo_slots"]
    ]


def test_fixed_recipe_dp_covers_every_photo_once_for_1_to_100() -> None:
    for count in range(1, 101):
        plans = plan_spreads(_photos(count))
        assigned = _assigned_ids(plans)
        assert len(assigned) == count
        assert len(set(assigned)) == count
        assert set(assigned) == {photo["id"] for photo in _photos(count)}
        assert all(sum(len(page["photo_slots"]) for page in spread["pages"]) <= 9 for spread in plans)


def test_each_spread_exposes_distinct_compatible_recipe_candidates() -> None:
    for count in (1, 2, 3, 4, 5, 6, 9):
        photos = _photos(count)
        candidates = candidate_recipes(photos)
        assert candidates
        assert len(candidates) <= 3
        assert len({candidate.key for candidate in candidates}) == len(candidates)
        assert all(candidate.photo_count == count for candidate in candidates)

    plans = plan_spreads(_photos(9))
    assert plans[0]["meta"]["candidate_recipe_keys"] == [candidate.key for candidate in candidate_recipes(_photos(9))]


def test_slot_geometry_and_crop_policy_keep_photos_complete_by_default() -> None:
    assert all(
        min(slot.width_mm, slot.height_mm) >= MIN_SLOT_SHORT_EDGE_MM
        and slot.width_mm * slot.height_mm >= MIN_SLOT_AREA_MM2
        for slots in TEMPLATE_SLOT_GEOMETRIES.values()
        for slot in slots
    )
    portrait = {"id": "portrait", "width": 3000, "height": 4500, "quality_score": 0.8}
    landscape = {"id": "landscape", "width": 4500, "height": 3000, "quality_score": 0.8}
    asym = get_recipe("asym_duo")
    assert asym is not None
    assignments = assign_recipe_slots([portrait, landscape], asym)
    slots = [slot for side in assignments.values() for slot in side]
    assert any(slot["fit_mode"] == "contain" for slot in slots)
    assert all(slot["fit_mode"] == "contain" or slot["crop_area"] <= 0.10 for slot in slots)

    facing = get_recipe("facing_duo")
    assert facing is not None
    square = {"id": "square", "width": 3600, "height": 3600, "quality_score": 0.9}
    square_two = {"id": "square-two", "width": 3200, "height": 3200, "quality_score": 0.7}
    hero_slots = [slot for side in assign_recipe_slots([square, square_two], facing).values() for slot in side]
    assert all(slot["fit_mode"] == "cover" for slot in hero_slots)


def test_embedding_mismatch_falls_back_and_requires_review() -> None:
    photos = _photos(3)
    features = {
        photos[0]["id"]: {
            "embedding": [1.0, 0.0],
            "embedding_provider": "a",
            "embedding_model": "m1",
            "embedding_dimension": 2,
        },
        photos[1]["id"]: {
            "embedding": [1.0, 0.0],
            "embedding_provider": "a",
            "embedding_model": "m2",
            "embedding_dimension": 2,
        },
    }
    plans = plan_spreads(photos, features=features)
    assert all(spread["needs_review"] for spread in plans)
    assert all(spread["meta"]["embedding_mode"] == "chronological_fallback" for spread in plans)


def test_v2_page_uses_focal_point_and_no_base64() -> None:
    html = generate_layout_html(
        {"template": "full_page", "css_class": "layout-full", "slots": 1},
        [
            {
                "id": "p1",
                "filename": "one.jpg",
                "src": "pixpress-asset://p1",
                "focal_x": 0.25,
                "focal_y": 0.75,
                "slot_key": "right_hero",
            }
        ],
        5,
        page_meta={
            "layout_version": "spread_v2",
            "style_key": "minimal_white",
            "side": "right",
            "text_side": "left",
            "display_page_number": 5,
        },
        style_presets=STYLE_PRESETS,
        print_spec={"book_size": "square_10inch", "bleed_mm": 3, "safe_margin_mm": 8},
    )
    assert "pixpress-asset://p1" in html
    assert "data:image" not in html
    assert "object-position:25.00% 75.00%" in html
    assert "object-fit:contain" in html
    assert "--page-width:260.0mm" in html


def test_print_profile_is_srgb_only() -> None:
    profile, warnings = normalize_print_spec({"color_profile": "cmyk"}, "square_10inch")
    assert profile["color_profile"] == "srgb"
    assert warnings
