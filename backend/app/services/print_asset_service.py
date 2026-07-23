from __future__ import annotations

import asyncio
from hashlib import sha1
from io import BytesIO
from typing import Any

from PIL import Image, ImageOps

from app.storage.file_store import get_file_storage


class PrintAssetService:
    """Build bounded sRGB JPEG assets, reused across text and style revisions."""

    def __init__(self) -> None:
        self.storage = get_file_storage()

    @staticmethod
    def logical_url(photo_id: str) -> str:
        return f"pixpress-asset://{photo_id}"

    @staticmethod
    def target_edge_px(target_edge_mm: float, page_dpi: int) -> int:
        return min(5000, max(640, round(target_edge_mm / 25.4 * page_dpi * 1.08)))

    @staticmethod
    def _derive(content: bytes, max_edge_px: int) -> bytes:
        with Image.open(BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode not in {"RGB", "L"}:
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")
            elif image.mode == "L":
                image = image.convert("RGB")
            image.thumbnail((max_edge_px, max_edge_px), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True, progressive=True, subsampling=1)
            return output.getvalue()

    async def build_assets(
        self,
        album_id: str,
        render_revision: int,
        photos: list[Any],
        *,
        page_dpi: int,
        trim_edge_mm: float,
        slot_edge_mm_by_photo: dict[str, float] | None = None,
    ) -> tuple[dict[str, str], dict[str, str], list[str]]:
        slot_edge_mm_by_photo = slot_edge_mm_by_photo or {}
        logical_sources: dict[str, str] = {}
        storage_keys: dict[str, str] = {}
        failures: list[str] = []
        semaphore = asyncio.Semaphore(4)

        async def build_one(photo) -> tuple[str, str] | None:
            try:
                # A 45 mm detail tile needs about 530 px at 300 DPI, not a
                # full 10-inch page derivative. Keep modest headroom for the
                # browser's rasterization without downscaling every source to
                # ~3300 px.
                target_edge_mm = float(slot_edge_mm_by_photo.get(str(photo.id), trim_edge_mm))
                max_edge_px = self.target_edge_px(target_edge_mm, page_dpi)
                source_signature = sha1(
                    f"{photo.storage_key}:{photo.width}:{photo.height}".encode("utf-8")
                ).hexdigest()[:12]
                artifact_name = f"print-assets/{photo.id}-{source_signature}-{max_edge_px}-q88.jpg"
                storage_key = f"albums/{album_id}/artifacts/{artifact_name}"
                try:
                    await self.storage.open_file(storage_key)
                    return photo.id, storage_key
                except FileNotFoundError:
                    pass
                async with semaphore:
                    original = await self.storage.open_file(photo.storage_key)
                    derivative = await asyncio.to_thread(self._derive, original, max_edge_px)
                stored = await self.storage.save_artifact(
                    album_id,
                    artifact_name,
                    derivative,
                    "image/jpeg",
                )
                return photo.id, stored.storage_key
            except Exception:  # noqa: BLE001
                return None

        results = await asyncio.gather(*(build_one(photo) for photo in photos))
        for photo, result in zip(photos, results):
            if result is None:
                failures.append(photo.id)
                continue
            photo_id, storage_key = result
            logical_sources[photo_id] = self.logical_url(photo_id)
            storage_keys[photo_id] = storage_key
        return logical_sources, storage_keys, failures
