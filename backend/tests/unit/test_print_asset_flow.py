from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("jwt")

from app.services.print_asset_service import PrintAssetService
from app.services.render_artifact_service import RenderArtifactService
from app.services.layout_service import LayoutService


def test_slot_sized_derivative_is_smaller_than_full_page_derivative() -> None:
    detail_px = PrintAssetService.target_edge_px(68, 300)
    full_page_px = PrintAssetService.target_edge_px(222, 300)

    assert 640 <= detail_px < full_page_px
    assert full_page_px == 2835


def test_contained_portrait_uses_visible_edge_not_wide_slot_edge() -> None:
    class Photo:
        width = 3000
        height = 4500

    class Link:
        photo_id = "portrait"
        photo = Photo()
        order_index = 0

    class Page:
        template = "grid_3"
        photo_links = [Link()]
        meta_json = {"slot_media": {"portrait": {"fit_mode": "contain"}}}

    targets = LayoutService._print_asset_targets([Page()], book_size="square_10inch")
    assert targets["portrait"] == 104


def test_materialize_print_assets_copies_without_opening_full_content(tmp_path) -> None:
    class CopyOnlyStorage:
        async def copy_to_path(self, storage_key: str, target_path) -> None:
            assert storage_key == "albums/a/artifacts/photo.jpg"
            target_path.write_bytes(b"jpeg")

    service = RenderArtifactService.__new__(RenderArtifactService)
    service.storage = CopyOnlyStorage()
    replacements = asyncio.run(
        service.materialize_print_assets({"print_assets": {"photo-1": "albums/a/artifacts/photo.jpg"}}, tmp_path)
    )

    assert replacements["pixpress-asset://photo-1"] == (tmp_path / "photo-1.jpg").as_uri()
    assert (tmp_path / "photo-1.jpg").read_bytes() == b"jpeg"
