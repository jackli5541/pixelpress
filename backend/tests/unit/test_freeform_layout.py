from types import SimpleNamespace

import pytest

from app.engines.layout_engine.freeform import (
    FreeformLayoutError,
    build_freeform_layout,
    validate_freeform_layout,
)
from app.engines.layout_engine.service import CSS_STYLES, generate_layout_html


def photo(photo_id: str, width: int, height: int):
    return SimpleNamespace(id=photo_id, width=width, height=height)


@pytest.mark.parametrize(
    "dimensions",
    [[(1600, 900)], [(900, 1600), (1600, 900)], [(300, 1800), (1200, 1200), (2000, 700)]],
)
def test_generated_layout_is_compact_and_validates(dimensions):
    photos = [photo(str(index), width, height) for index, (width, height) in enumerate(dimensions)]
    layout = build_freeform_layout(photos, {"title": "旅行", "captions": [{"photo_id": "0", "text": "雪山"}]})

    validated = validate_freeform_layout(layout, {item.id: item for item in photos})

    assert validated["layout_version"] == 3
    assert validated["description"]["text"] == "旅行\n雪山"
    assert validated["description"]["height"] >= 0.06
    assert len(validated["elements"]) == len(photos)
    assert all(item["fit"] in {"cover", "contain"} for item in validated["elements"])


def test_validation_rejects_crop_overlap_and_page_number_band():
    photos = {"a": photo("a", 1000, 1000), "b": photo("b", 1000, 1000)}
    layout = build_freeform_layout(list(photos.values()))
    layout["elements"][1]["x"] = layout["elements"][0]["x"]
    layout["elements"][1]["y"] = layout["elements"][0]["y"]
    with pytest.raises(FreeformLayoutError, match="overlap"):
        validate_freeform_layout(layout, photos)

    layout = build_freeform_layout([photos["a"]])
    layout["elements"][0]["fit"] = "stretch"
    with pytest.raises(FreeformLayoutError, match="fit"):
        validate_freeform_layout(layout, {"a": photos["a"]})

    layout = build_freeform_layout([photos["a"]])
    layout["elements"][0]["y"] = 0.9
    with pytest.raises(FreeformLayoutError, match="safe content"):
        validate_freeform_layout(layout, {"a": photos["a"]})


def test_templates_produce_distinct_geometry_and_v2_layout_upgrades_in_place():
    photos = [photo("a", 1200, 900), photo("b", 900, 1200)]
    rows = build_freeform_layout(photos, template="half_half")
    columns = build_freeform_layout(photos, template="two_column")
    assert [(item["x"], item["y"], item["width"], item["height"]) for item in rows["elements"]] != [
        (item["x"], item["y"], item["width"], item["height"]) for item in columns["elements"]
    ]

    legacy = {**rows, "layout_version": 2}
    for item in legacy["elements"]:
        item.pop("fit")
    legacy["description"].pop("height")
    upgraded = build_freeform_layout(photos, legacy, template="two_column")
    assert upgraded["layout_version"] == 3
    assert upgraded["elements"][0]["x"] == rows["elements"][0]["x"]
    assert upgraded["elements"][0]["fit"] == "contain"
    assert upgraded["description"]["height"] >= 0.06


def test_html_uses_freeform_geometry_without_photo_placeholders_or_captions():
    photos = [{"id": "a", "width": 1600, "height": 900, "url": "/a.jpg", "filename": "a.jpg", "custom_caption": "旧说明"}]
    html = generate_layout_html(
        {"template": "full_page", "css_class": "layout-full"},
        photos,
        page_meta={"title": "标题", "subtitle": "正文"},
    )

    assert 'class="freeform-photo"' in html
    assert 'class="page-description"' in html
    assert 'class="photo-caption"' not in html
    assert 'class="page-copy' not in html
    assert "object-fit: var(--photo-fit, contain)" in CSS_STYLES
    assert "--photo-fit:" in html
    assert "background: transparent" in CSS_STYLES
