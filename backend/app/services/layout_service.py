from __future__ import annotations

import asyncio
import base64
import mimetypes
from io import BytesIO
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image, ImageOps

from app.common.enums import AlbumStatus
from app.ai.types import ImagePayload
from app.core.config import get_settings
from app.engines.layout_engine.prompt_pipeline import recommend_layout_with_ai
from app.engines.layout_engine.service import (
    CSS_STYLES,
    LAYOUT_TEMPLATES,
    generate_album_closer_html,
    generate_blank_page_html,
    generate_chapter_divider_html,
    generate_cover_html,
    generate_layout_html,
    plan_pages,
)
from app.engines.layout_engine.templates import STYLE_PRESETS, build_template_catalog
from app.engines.layout_engine.spread_planner import (
    TEMPLATE_SLOT_GEOMETRIES,
    assign_recipe_slots,
    get_recipe,
    layout_catalog,
    normalize_style_key,
    plan_spreads,
)
from app.engines.layout_engine.spread_copy import generate_chapter_spread_copy
from app.repositories.album_repo import AlbumRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.page_repo import PageRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.photo_chapter_feature_repo import PhotoChapterFeatureRepository
from app.repositories.spread_repo import SpreadRepository
from app.repositories.task_repo import TaskRepository
from app.services.project_ai_config_service import ProjectAIConfigService
from app.services.photo_selection import is_photo_included
from app.services.print_asset_service import PrintAssetService
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_page, serialize_spread
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService
from app.storage.file_store import get_file_storage

PLAN_PIPELINE_NAME = "planning"
RENDER_PIPELINE_NAME = "rendering"
PIPELINE_VERSION = "p0-async-v1"
PLAN_TASK_TYPE = "plan_pages"
RENDER_TASK_TYPE = "render_layout"
PLAN_JOB_NAME = "run_plan_pages_job"
RENDER_JOB_NAME = "run_render_layout_job"


class LayoutService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.chapter_repo = ChapterRepository(session)
        self.page_repo = PageRepository(session)
        self.photo_repo = PhotoRepository(session)
        self.feature_repo = PhotoChapterFeatureRepository(session)
        self.spread_repo = SpreadRepository(session)
        self.task_repo = TaskRepository(session)
        self.storage = get_file_storage()
        self.ai_config_service = ProjectAIConfigService(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.render_artifacts = RenderArtifactService()
        self.print_assets = PrintAssetService()

    async def _clear_render_artifacts(self, album) -> None:
        await clear_render_artifacts(album, self.render_artifacts, stale_status=AlbumStatus.PLANNED)


    async def _update_task_debug(
        self,
        task_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        result_payload: dict | None = None,
        debug_payload: dict | None = None,
    ) -> None:
        task = await self.task_repo.get_task(task_id)
        if task is None:
            return
        updates = {}
        if provider is not None:
            updates["provider"] = provider
        if model is not None:
            updates["model"] = model
        if result_payload is not None:
            updates["result_payload"] = result_payload
        if debug_payload is not None:
            merged_debug: dict[str, Any] = dict(task.debug_payload or {})
            for key, value in debug_payload.items():
                if isinstance(value, dict) and isinstance(merged_debug.get(key), dict):
                    merged_debug[key] = {**merged_debug[key], **value}
                else:
                    merged_debug[key] = value
            updates["debug_payload"] = merged_debug
        if updates:
            await self.task_repo.update_task(task, updates)

    @staticmethod
    def _default_print_spec(album) -> dict:
        return album.print_spec_json or {
            "book_size": album.book_size,
            "bleed_mm": 3,
            "safe_margin_mm": 8,
            "page_dpi": 300,
            "allow_spread": True,
            "color_profile": "srgb",
        }

    @staticmethod
    def _album_style_key(album) -> str:
        if getattr(album, "layout_version", "legacy_page_v1") == "spread_v2":
            return normalize_style_key(album.theme_style)
        return album.theme_style if album.theme_style in STYLE_PRESETS else "warm_family"

    @staticmethod
    def _build_default_page_meta(album, *, title: str = "", subtitle: str = "", photo_ids: list[str] | None = None, page_role: str = "standard") -> dict[str, Any]:
        return {
            "style_key": LayoutService._album_style_key(album),
            "page_role": page_role,
            "title": title,
            "subtitle": subtitle,
            "captions": [{"photo_id": pid, "text": ""} for pid in (photo_ids or [])],
            "confidence": 0.0,
            "reason": "rule fallback",
            "alternatives": [],
        }

    @staticmethod
    def _content_type_for(photo) -> str:
        guessed = mimetypes.guess_type(photo.filename or "")[0]
        return photo.content_type or guessed or "image/jpeg"

    async def _build_embedded_photo_sources(self, photos_by_id: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
        embedded: dict[str, str] = {}
        failures: list[str] = []
        for photo_id, photo in photos_by_id.items():
            try:
                payload = await self.storage.open_file(photo.storage_key)
                data = base64.b64encode(payload).decode("ascii")
                embedded[photo_id] = f"data:{self._content_type_for(photo)};base64,{data}"
            except Exception:  # noqa: BLE001
                embedded[photo_id] = photo.url
                failures.append(photo_id)
        return embedded, failures

    @staticmethod
    def _build_preview_photo_sources(photos_by_id: dict[str, Any]) -> dict[str, str]:
        return {
            photo_id: photo.url
            for photo_id, photo in photos_by_id.items()
            if getattr(photo, "url", None)
        }

    def _page_photo_payloads(self, page_photos: list[Any], embedded_sources: dict[str, str] | None = None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for photo in page_photos:
            item = {
                "id": photo.id,
                "url": photo.url,
                "filename": photo.filename,
                "custom_caption": photo.custom_caption,
            }
            if embedded_sources is not None:
                item["src"] = embedded_sources.get(photo.id, photo.url)
            payloads.append(item)
        return payloads

    def _spread_page_photo_payloads(self, page, sources: dict[str, str]) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        slot_media = (page.meta_json or {}).get("slot_media") or {}
        for link in sorted(page.photo_links, key=lambda item: item.order_index):
            photo = link.photo
            if photo is None:
                continue
            payloads.append(
                {
                    "id": photo.id,
                    "url": photo.url,
                    "src": sources.get(photo.id, photo.url),
                    "filename": photo.filename,
                    "custom_caption": photo.custom_caption,
                    "slot_key": link.slot_key,
                    "focal_x": link.focal_x,
                    "focal_y": link.focal_y,
                    **dict(slot_media.get(str(photo.id)) or {}),
                }
            )
        return payloads

    @staticmethod
    def _slot_media_meta(slots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        allowed = {"fit_mode", "crop_area", "crop_edge", "slot_width_mm", "slot_height_mm"}
        return {
            str(slot["photo_id"]): {key: slot[key] for key in allowed if key in slot}
            for slot in slots
            if slot.get("photo_id")
        }

    @staticmethod
    def _print_asset_targets(pages: list[Any], *, book_size: str) -> dict[str, float]:
        """Return the largest physical media edge needed for every unique photo."""

        page_edge_mm = 254.0 if book_size == "square_10inch" else 210.0
        scale = page_edge_mm / 254.0
        targets: dict[str, float] = {}
        for page in pages:
            geometries = TEMPLATE_SLOT_GEOMETRIES.get(page.template, ())
            slot_media = (page.meta_json or {}).get("slot_media") or {}
            for index, link in enumerate(sorted(page.photo_links, key=lambda item: item.order_index)):
                if index >= len(geometries):
                    continue
                geometry = geometries[index]
                photo = link.photo
                if photo is None:
                    continue
                fit_mode = (slot_media.get(str(link.photo_id)) or {}).get("fit_mode", "contain")
                photo_aspect = float(photo.width or 0) / float(photo.height or 1)
                if fit_mode == "cover":
                    visible_edge_mm = max(geometry.width_mm, geometry.height_mm)
                elif photo_aspect >= geometry.aspect_ratio:
                    visible_edge_mm = geometry.width_mm
                else:
                    visible_edge_mm = geometry.height_mm
                targets[str(link.photo_id)] = max(
                    targets.get(str(link.photo_id), 0.0),
                    visible_edge_mm * scale,
                )
        return targets

    @staticmethod
    def _build_album_document(album_name: str, html_parts: list[str]) -> str:
        return (
            "<!DOCTYPE html>"
            '<html lang="zh-CN"><head><meta charset="utf-8" />'
            f"<title>{album_name}</title><style>{CSS_STYLES}</style></head><body>"
            f'{"".join(html_parts)}'
            "</body></html>"
        )

    async def _persist_render_artifacts(self, album, preview_html: str, print_html: str, manifest: dict[str, Any]) -> tuple[str, str, str]:
        return await self.render_artifacts.persist_render_bundle(album, preview_html, print_html, manifest)

    async def load_preview_html(self, album_id: str) -> str | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        return await self.render_artifacts.load_preview_html(album)

    async def build_style_sample(
        self,
        album_id: str,
        style_key: str,
        *,
        spread_id: str | None = None,
        recipe_key: str | None = None,
    ) -> str | None:
        album = await self.album_repo.get_album(album_id)
        if album is None or getattr(album, "layout_version", "legacy_page_v1") != "spread_v2":
            return None
        selected_style = normalize_style_key(style_key)
        spreads = await self.spread_repo.list_spreads(album_id)
        if spread_id:
            spreads = [spread for spread in spreads if spread.id == spread_id]
        else:
            spreads = spreads[:2]
        if not spreads:
            return None
        print_spec = self._default_print_spec(album)
        pages_html: list[str] = []
        for spread in spreads:
            candidate_recipe = get_recipe(recipe_key) if recipe_key else None
            candidate_keys = list((spread.meta_json or {}).get("candidate_recipe_keys") or [])
            if candidate_recipe and (
                candidate_recipe.photo_count != sum(len(page.photo_links) for page in spread.pages)
                or candidate_recipe.key not in candidate_keys
            ):
                candidate_recipe = None
            photo_by_id = {
                link.photo_id: link.photo
                for page in spread.pages
                for link in page.photo_links
                if link.photo is not None
            }
            candidate_slots = (
                assign_recipe_slots([self._spread_photo_payload(photo) for photo in photo_by_id.values()], candidate_recipe)
                if candidate_recipe
                else None
            )
            for page in sorted(spread.pages, key=lambda item: 0 if item.side == "left" else 1):
                template_key = (
                    candidate_recipe.left_template if candidate_recipe and page.side == "left"
                    else candidate_recipe.right_template if candidate_recipe
                    else page.template
                )
                template = LAYOUT_TEMPLATES.get(template_key, LAYOUT_TEMPLATES["grid_3"])
                if candidate_slots is not None:
                    page_photos = []
                    for slot in candidate_slots[page.side]:
                        photo = photo_by_id.get(slot["photo_id"])
                        if photo is None:
                            continue
                        page_photos.append({
                            "id": photo.id,
                            "url": photo.url,
                            "src": photo.url,
                            "filename": photo.filename,
                            "custom_caption": photo.custom_caption,
                            **slot,
                        })
                else:
                    page_photos = self._spread_page_photo_payloads(page, self._build_preview_photo_sources(photo_by_id))
                page_meta = dict(page.meta_json or {})
                page_meta.update(
                    {
                        "layout_version": "spread_v2",
                        "style_key": selected_style,
                        "side": page.side,
                        "headline": spread.headline,
                        "body": spread.body,
                        "text_side": candidate_recipe.text_side if candidate_recipe else (spread.meta_json or {}).get("text_side", "none"),
                        "display_page_number": None,
                    }
                )
                pages_html.append(
                    generate_layout_html(
                        {
                            "template": template_key,
                            "css_class": template["css_class"],
                            "slots": template["slots"],
                        },
                        page_photos,
                        page.page_number,
                        page_meta=page_meta,
                        style_presets=STYLE_PRESETS,
                        print_spec=print_spec,
                    )
                )
        document = self._build_album_document(album.name, pages_html)
        return self.render_artifacts._rewrite_preview_html(album, document)

    async def load_print_html(self, album_id: str) -> str | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        return await self.render_artifacts.load_print_html(album)

    async def list_pages(self, album_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        pages = await self.page_repo.list_pages(album_id)
        return [serialize_page(page) for page in pages]

    @staticmethod
    def get_layout_catalog() -> dict[str, Any]:
        return layout_catalog()

    async def list_spreads(self, album_id: str) -> list[dict[str, Any]] | None:
        if await self.album_repo.get_album(album_id) is None:
            return None
        return [serialize_spread(spread) for spread in await self.spread_repo.list_spreads(album_id)]

    async def update_spread(self, album_id: str, spread_id: str, payload: dict[str, Any]):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None, "album"
        spread = await self.spread_repo.get_spread(album_id, spread_id)
        if spread is None:
            return None, "spread"
        updates = {
            key: value
            for key, value in payload.items()
            if key in {"headline", "body", "needs_review"} and value is not None
        }
        if "headline" in updates:
            updates["headline"] = str(updates["headline"]).strip()[:18]
        if "body" in updates:
            updates["body"] = str(updates["body"]).strip()[:70]
        requested_recipe = payload.get("recipe_key")
        if requested_recipe and requested_recipe != spread.recipe_key:
            recipe = get_recipe(str(requested_recipe))
            current_count = sum(len(page.photo_links) for page in spread.pages)
            candidate_keys = list((spread.meta_json or {}).get("candidate_recipe_keys") or [])
            if recipe is None or recipe.photo_count != current_count or recipe.key not in candidate_keys:
                return None, "recipe"
            updates["recipe_key"] = recipe.key
            meta = dict(spread.meta_json or {})
            meta["text_side"] = recipe.text_side
            meta["candidate_rank"] = candidate_keys.index(recipe.key)
            updates["meta_json"] = meta
            photos_by_id = {
                link.photo_id: link.photo
                for page in spread.pages
                for link in page.photo_links
                if link.photo is not None
            }
            assignments = assign_recipe_slots(
                [self._spread_photo_payload(photo) for photo in photos_by_id.values()],
                recipe,
            )
            for page in spread.pages:
                page_slots = assignments[page.side]
                page_meta = dict(page.meta_json or {})
                page_meta.update(
                    {
                        "spread_recipe": recipe.key,
                        "text_side": recipe.text_side,
                        "slot_media": self._slot_media_meta(page_slots),
                    }
                )
                await self.page_repo.update_page(
                    page,
                    {"template": recipe.left_template if page.side == "left" else recipe.right_template, "meta_json": page_meta},
                    [item["photo_id"] for item in page_slots],
                    page_slots,
                )
        slots = {str(item.get("photo_id")): item for item in (payload.get("photo_slots") or []) if item.get("photo_id")}
        for page in spread.pages:
            for link in page.photo_links:
                item = slots.get(link.photo_id)
                if item is None:
                    continue
                link.focal_x = min(max(float(item.get("focal_x", link.focal_x)), 0.0), 1.0)
                link.focal_y = min(max(float(item.get("focal_y", link.focal_y)), 0.0), 1.0)
        await self.spread_repo.update_spread(spread, updates)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        refreshed = await self.spread_repo.get_spread(album_id, spread_id)
        return serialize_spread(refreshed), None

    async def regenerate_spread_copy(self, album_id: str, spread_id: str):
        spread = await self.spread_repo.get_spread(album_id, spread_id)
        if spread is None:
            return None
        chapter = await self.chapter_repo.get_chapter(album_id, spread.chapter_id) if spread.chapter_id else None
        headline = (chapter.name if chapter else "这一段记忆")[:18]
        body = (chapter.description if chapter else "")[:70]
        settings = get_settings()
        if settings.ai_enabled and settings.ai_mode_b3 != "rule":
            try:
                connection = await self.ai_config_service.resolve_for_album(
                    album_id,
                    stage="layout",
                    model_hint=settings.ai_model_b3,
                    provider_hint=settings.ai_provider_b3,
                )
                page_plans = []
                photo_payloads: dict[str, dict[str, Any]] = {}
                for page in sorted(spread.pages, key=lambda item: 0 if item.side == "left" else 1):
                    slots = []
                    for link in sorted(page.photo_links, key=lambda item: item.order_index):
                        slots.append({"photo_id": link.photo_id, "slot_key": link.slot_key})
                        if link.photo is not None:
                            photo_payloads[link.photo_id] = self._spread_photo_payload(link.photo)
                    page_plans.append({"side": page.side, "photo_slots": slots})
                single_plan = {"spread_number": spread.spread_number, "headline": headline, "body": body, "pages": page_plans}
                visual_evidence = await self._build_spread_contact_sheets(
                    [single_plan],
                    {
                        link.photo_id: link.photo
                        for page in spread.pages
                        for link in page.photo_links
                        if link.photo is not None
                    },
                )
                generated, _ = await generate_chapter_spread_copy(
                    [single_plan],
                    photo_payloads,
                    chapter_name=chapter.name if chapter else "",
                    chapter_description=chapter.description if chapter else "",
                    provider_connection=connection,
                    visual_evidence=visual_evidence,
                )
                if generated:
                    headline = generated[0]["headline"]
                    body = generated[0]["body"]
            except Exception:  # noqa: BLE001
                pass
        return (await self.update_spread(album_id, spread_id, {"headline": headline, "body": body}))[0]

    async def create_page(self, album_id: str, payload: dict):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        pages = await self.page_repo.list_pages(album_id)
        page = await self.page_repo.create_page(
            {
                "album_id": album_id,
                "chapter_id": payload.get("chapter_id"),
                "page_number": len(pages) + 1,
                "template": payload.get("template", "grid_3"),
                "html": "",
                "status": "draft",
                "meta_json": payload.get("meta"),
            },
            payload.get("photo_ids", []),
        )
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        return serialize_page(page)

    async def update_page(self, album_id: str, page_id: str, payload: dict):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None, "album"
        page = await self.page_repo.get_page(album_id, page_id)
        if page is None:
            return None, "page"
        photo_ids = payload.pop("photo_ids", None)
        if "meta" in payload:
            payload["meta_json"] = payload.pop("meta")
        updated = await self.page_repo.update_page(page, payload, photo_ids)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        return serialize_page(updated), None

    async def delete_page(self, album_id: str, page_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return "album"
        page = await self.page_repo.get_page(album_id, page_id)
        if page is None:
            return "page"
        await self.page_repo.delete_page(page)
        remaining = await self.page_repo.list_pages(album_id)
        for index, item in enumerate(remaining, 1):
            await self.page_repo.update_page(item, {"page_number": index}, None)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        return None

    async def move_photos(self, album_id: str, photo_ids: list[str], target_page_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None, "album"
        pages = await self.page_repo.list_pages(album_id)
        target = next((page for page in pages if page.id == target_page_id), None)
        if target is None:
            return None, "target"
        for page in pages:
            current_ids = [link.photo_id for link in sorted(page.photo_links, key=lambda item: item.order_index)]
            if page.id == target_page_id:
                existing = set(current_ids)
                for photo_id in photo_ids:
                    if photo_id not in existing:
                        current_ids.append(photo_id)
                        existing.add(photo_id)
            else:
                current_ids = [pid for pid in current_ids if pid not in photo_ids]
            await self.page_repo.update_page(page, {}, current_ids)
        album.content_revision += 1
        await self._clear_render_artifacts(album)
        await self.session.commit()
        refreshed = await self.page_repo.get_page(album_id, target_page_id)
        return {"target_page": serialize_page(refreshed), "moved_count": len(photo_ids)}, None

    async def request_plan_pages(self, album_id: str, user_id: str | None, layout_version: str | None = None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        if layout_version == "spread_v2" and album.layout_version != "spread_v2":
            album.layout_version = "spread_v2"
            album.theme_style = normalize_style_key(album.theme_style)
            album.content_revision += 1
            await self._clear_render_artifacts(album)
            await self.session.flush()
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=PLAN_TASK_TYPE,
            task_params=None,
            idempotency_key=f"plan:{album_id}:{album.content_revision}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=PLAN_JOB_NAME,
            pipeline_name=PLAN_PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            max_attempts=get_settings().queue_max_attempts,
        )

    @staticmethod
    def _spread_photo_payload(photo) -> dict[str, Any]:
        return {
            "id": photo.id,
            "width": photo.width,
            "height": photo.height,
            "taken_at": photo.taken_at,
            "gps_latitude": photo.gps_latitude,
            "gps_longitude": photo.gps_longitude,
            "quality_score": photo.quality_score,
            "cleaning_features": photo.cleaning_features,
            "custom_caption": photo.custom_caption,
        }

    async def _build_spread_contact_sheets(
        self,
        plans: list[dict[str, Any]],
        photos_by_id: dict[str, Any],
    ) -> list[ImagePayload]:
        """Build small contact sheets so one chapter call can see every spread."""

        semaphore = asyncio.Semaphore(4)

        async def build(plan: dict[str, Any]) -> ImagePayload | None:
            photo_ids = [
                str(slot["photo_id"])
                for page in plan["pages"]
                for slot in page["photo_slots"]
            ]
            try:
                async with semaphore:
                    contents = await asyncio.gather(
                        *(self.storage.open_file(photos_by_id[photo_id].storage_key) for photo_id in photo_ids)
                    )
                thumbs: list[Image.Image] = []
                for content in contents:
                    with Image.open(BytesIO(content)) as source:
                        image = ImageOps.exif_transpose(source).convert("RGB")
                        image.thumbnail((220, 220), Image.Resampling.LANCZOS)
                        thumbs.append(image.copy())
                if not thumbs:
                    return None
                columns = min(3, len(thumbs))
                rows = (len(thumbs) + columns - 1) // columns
                canvas = Image.new("RGB", (columns * 228 + 8, rows * 228 + 8), "white")
                for index, image in enumerate(thumbs):
                    x = 8 + (index % columns) * 228 + (220 - image.width) // 2
                    y = 8 + (index // columns) * 228 + (220 - image.height) // 2
                    canvas.paste(image, (x, y))
                output = BytesIO()
                canvas.save(output, format="JPEG", quality=76, optimize=True)
                return ImagePayload(
                    media_type="image/jpeg",
                    data_base64=base64.b64encode(output.getvalue()).decode("ascii"),
                    width=canvas.width,
                    height=canvas.height,
                    filename=f"spread-{plan['spread_number']}-contact.jpg",
                )
            except Exception:  # noqa: BLE001
                return None

        sheets = await asyncio.gather(*(build(plan) for plan in plans))
        return [sheet for sheet in sheets if sheet is not None]

    async def _execute_spread_plan(self, task_id: str, album, keep_photos: list[Any], chapters: list[Any], started: float):
        settings = get_settings()
        photos_by_id = {photo.id: photo for photo in keep_photos}
        feature_records = await self.feature_repo.list_successful_for_photos(list(photos_by_id))
        features = {
            item.photo_id: {
                "embedding": list(item.embedding or []),
                "embedding_provider": item.embedding_provider,
                "embedding_model": item.embedding_model,
                "embedding_dimension": item.embedding_dimension,
            }
            for item in feature_records
        }
        await self.album_repo.clear_album_pages(album.id)
        await self.spread_repo.clear_album_spreads(album.id)
        created_pages: list[dict[str, Any]] = []
        assigned_ids: set[str] = set()
        global_page_no = 0
        global_spread_no = 0

        async def persist_plans(plans: list[dict[str, Any]], chapter_id: str | None) -> None:
            nonlocal global_page_no, global_spread_no
            for plan in plans:
                global_spread_no += 1
                spread = await self.spread_repo.create_spread(
                    {
                        "album_id": album.id,
                        "chapter_id": chapter_id,
                        "spread_number": global_spread_no,
                        "recipe_key": plan["recipe_key"],
                        "headline": plan["headline"],
                        "body": plan["body"],
                        "needs_review": plan["needs_review"],
                        "planning_version": plan["planning_version"],
                        "meta_json": plan["meta"],
                    }
                )
                for page_plan in plan["pages"]:
                    global_page_no += 1
                    slots = page_plan["photo_slots"]
                    photo_ids = [item["photo_id"] for item in slots]
                    assigned_ids.update(photo_ids)
                    page_meta = self._build_default_page_meta(album, photo_ids=photo_ids)
                    generated_captions = {
                        item["photo_id"]: item["text"]
                        for item in plan["meta"].get("captions", [])
                        if item.get("photo_id") in photo_ids
                    }
                    page_meta["captions"] = [
                        {"photo_id": photo_id, "text": generated_captions.get(photo_id, "")}
                        for photo_id in photo_ids
                    ]
                    page_meta.update(
                        {
                            "spread_number": global_spread_no,
                            "spread_recipe": plan["recipe_key"],
                            "side": page_plan["side"],
                            "headline": plan["headline"],
                            "body": plan["body"],
                            "text_side": plan["meta"]["text_side"],
                            "slot_media": self._slot_media_meta(slots),
                        }
                    )
                    page = await self.page_repo.create_page(
                        {
                            "album_id": album.id,
                            "chapter_id": chapter_id,
                            "spread_id": spread.id,
                            "side": page_plan["side"],
                            "page_number": global_page_no,
                            "template": page_plan["template"],
                            "html": "",
                            "status": "draft",
                            "meta_json": page_meta,
                        },
                        photo_ids,
                        slots,
                    )
                    created_pages.append(serialize_page(page))

        for chapter in chapters:
            chapter_ids = [link.photo_id for link in sorted(chapter.photo_links, key=lambda item: item.order_index)]
            chapter_photos = [photos_by_id[photo_id] for photo_id in chapter_ids if photo_id in photos_by_id]
            plans = plan_spreads(
                [self._spread_photo_payload(photo) for photo in chapter_photos],
                features=features,
                chapter_name=chapter.name,
                chapter_description=chapter.description,
            )
            if settings.ai_enabled and settings.ai_mode_b3 != "rule" and plans:
                try:
                    connection = await self.ai_config_service.resolve_for_album(
                        album.id,
                        stage="layout",
                        model_hint=settings.ai_model_b3,
                        provider_hint=settings.ai_provider_b3,
                    )
                    visual_evidence = await self._build_spread_contact_sheets(
                        plans,
                        {photo.id: photo for photo in chapter_photos},
                    )
                    copy_items, copy_debug = await generate_chapter_spread_copy(
                        plans,
                        {photo.id: self._spread_photo_payload(photo) for photo in chapter_photos},
                        chapter_name=chapter.name,
                        chapter_description=chapter.description,
                        provider_connection=connection,
                        visual_evidence=visual_evidence,
                    )
                    copy_by_number = {item["spread_number"]: item for item in copy_items}
                    for plan in plans:
                        copy = copy_by_number.get(plan["spread_number"])
                        if copy:
                            plan["headline"] = copy["headline"]
                            plan["body"] = copy["body"]
                            plan["meta"]["captions"] = copy["captions"]
                    await self._update_task_debug(task_id, debug_payload={"spread_copy": copy_debug})
                except Exception as exc:  # noqa: BLE001
                    await self._update_task_debug(
                        task_id,
                        debug_payload={"spread_copy": {"fallback": True, "reason": str(exc)[:255]}},
                    )
            await persist_plans(plans, chapter.id)

        orphan_photos = [photo for photo in keep_photos if photo.id not in assigned_ids]
        if orphan_photos:
            await persist_plans(
                plan_spreads([self._spread_photo_payload(photo) for photo in orphan_photos], features=features),
                None,
            )

        album.status = AlbumStatus.PLANNED
        album.content_revision += 1
        review_count = sum(1 for spread in await self.spread_repo.list_spreads(album.id) if spread.needs_review)
        metrics = {
            "duration_ms": round((perf_counter() - started) * 1000),
            "page_count": len(created_pages),
            "spread_count": global_spread_no,
            "chapter_count": len(chapters),
            "needs_review_count": review_count,
            "embedding_feature_count": len(features),
        }
        await self.task_service.complete_success(
            task_id,
            result_payload={key: value for key, value in metrics.items() if key != "duration_ms"},
            debug_payload={"stage": "persisting_spreads", "reason": "spread_plan_succeeded", "layout_version": "spread_v2"},
            metrics_payload=metrics,
            result_revision=album.content_revision,
        )
        await self.session.commit()
        return {"pages": created_pages, "spread_count": global_spread_no}

    async def execute_plan_pages(self, task_id: str, album_id: str):
        started = perf_counter()
        settings = get_settings()
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_album_context", 10)
            photos = await self.photo_repo.list_photos(album_id)
            keep_photos = [photo for photo in photos if is_photo_included(photo)]
            if not keep_photos:
                album.status = AlbumStatus.PLANNED
                album.content_revision += 1
                await self.task_service.complete_success(
                    task_id,
                    result_payload={"page_count": 0, "chapter_count": 0},
                    metrics_payload={"duration_ms": round((perf_counter() - started) * 1000), "page_count": 0, "chapter_count": 0},
                    result_revision=album.content_revision,
                )
                await self.session.commit()
                return {"pages": []}

            photos_by_id = {photo.id: photo for photo in keep_photos}
            chapters = await self.chapter_repo.list_chapters(album_id)
            if album.layout_version == "spread_v2":
                return await self._execute_spread_plan(task_id, album, keep_photos, chapters, started)
            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "planning_pages", 30)
            created = []
            global_page_no = 0
            assigned_ids: set[str] = set()
            template_catalog = build_template_catalog(LAYOUT_TEMPLATES)
            print_spec = self._default_print_spec(album)
            debug_payload: dict[str, Any] = {"mode": settings.ai_mode_b3, "fallback_used": False, "stage": "planning_pages", "reason": "pending", "pages": []}
            provider_connection = None
            if settings.ai_enabled and settings.ai_mode_b3 != "rule":
                provider_connection = await self.ai_config_service.resolve_for_album(
                    album_id,
                    stage="layout",
                    model_hint=settings.ai_model_b3,
                    provider_hint=settings.ai_provider_b3,
                )
                debug_payload.update(
                    {
                        "provider_debug": {
                            "source": provider_connection.source,
                            "project_id": provider_connection.project_id,
                            "config_id": provider_connection.config_id,
                        }
                    }
                )

            await self.album_repo.clear_album_pages(album_id)
            for chapter in chapters:
                chapter_photo_ids = [link.photo_id for link in sorted(chapter.photo_links, key=lambda item: item.order_index)]
                chapter_photos = [photos_by_id[pid] for pid in chapter_photo_ids if pid in photos_by_id]
                if not chapter_photos:
                    continue
                chapter_pages = plan_pages(
                    [{"id": photo.id, "width": photo.width, "height": photo.height} for photo in chapter_photos],
                    photos_per_page=3,
                )
                for page_index, page_plan in enumerate(chapter_pages):
                    global_page_no += 1
                    ordered_photo_ids = list(page_plan["photo_ids"])
                    page_role_hint = "opening" if page_index == 0 else ("closing" if page_index == len(chapter_pages) - 1 else "standard")
                    page_meta = self._build_default_page_meta(
                        album,
                        title=chapter.name,
                        subtitle=chapter.description,
                        photo_ids=ordered_photo_ids,
                        page_role="opening" if page_index == 0 else "standard",
                    )
                    if settings.ai_enabled and settings.ai_mode_b3 != "rule":
                        candidate_photos = [
                            {
                                "id": photo.id,
                                "filename": photo.filename,
                                "width": photo.width,
                                "height": photo.height,
                                "scene_tags": photo.scene_tags,
                                "quality_score": photo.quality_score,
                            }
                            for photo in chapter_photos
                            if photo.id in page_plan["photo_ids"]
                        ]
                        try:
                            ai_result, provider_debug = await recommend_layout_with_ai(
                                candidate_photos,
                                template_catalog,
                                chapter_name=chapter.name,
                                chapter_description=chapter.description,
                                page_role_hint=page_role_hint,
                                print_spec=print_spec,
                                provider_connection=provider_connection,
                            )
                            page_plan["template"]["template"] = ai_result.template_key
                            ordered_photo_ids = ai_result.ordered_photo_ids
                            page_meta = ai_result.model_dump()
                            debug_payload["stage"] = "calling_layout_ai"
                            debug_payload["reason"] = "ai_layout_succeeded"
                            debug_payload["pages"].append({"page_number": global_page_no, **provider_debug})
                            await self._update_task_debug(
                                task_id,
                                provider=provider_debug.get("provider"),
                                model=provider_debug.get("model"),
                                debug_payload=debug_payload,
                            )
                        except Exception as exc:  # noqa: BLE001
                            if settings.ai_fallback_on_error:
                                debug_payload["stage"] = "calling_layout_ai"
                                debug_payload["reason"] = "provider_failed_rule_fallback"
                                debug_payload["fallback_used"] = True
                                debug_payload["pages"].append({"page_number": global_page_no, "error": str(exc)[:255], "fallback": "rule", "exception_type": exc.__class__.__name__})
                                page_meta["reason"] = "rule fallback"
                            else:
                                await self.task_service.complete_failure(
                                    task_id,
                                    error_code="provider_failed",
                                    error_message=str(exc)[:500],
                                    retryable=False,
                                    debug_payload={
                                        "mode": settings.ai_mode_b3,
                                        "stage": "calling_layout_ai",
                                        "reason": "provider_failed",
                                        "exception_type": exc.__class__.__name__,
                                        "error": str(exc)[:255],
                                    },
                                )
                                await self.session.commit()
                                return None
                    for pid in ordered_photo_ids:
                        assigned_ids.add(pid)
                    page = await self.page_repo.create_page(
                        {
                            "album_id": album_id,
                            "chapter_id": chapter.id,
                            "page_number": global_page_no,
                            "template": page_plan["template"]["template"],
                            "html": "",
                            "status": "draft",
                            "meta_json": page_meta,
                        },
                        ordered_photo_ids,
                    )
                    created.append(serialize_page(page))

            orphan_photos = [photo for photo in keep_photos if photo.id not in assigned_ids]
            if orphan_photos:
                orphan_pages = plan_pages(
                    [{"id": photo.id, "width": photo.width, "height": photo.height} for photo in orphan_photos],
                    photos_per_page=3,
                )
                for page_plan in orphan_pages:
                    global_page_no += 1
                    ordered_photo_ids = list(page_plan["photo_ids"])
                    page = await self.page_repo.create_page(
                        {
                            "album_id": album_id,
                            "chapter_id": None,
                            "page_number": global_page_no,
                            "template": page_plan["template"]["template"],
                            "html": "",
                            "status": "draft",
                            "meta_json": self._build_default_page_meta(album, photo_ids=ordered_photo_ids),
                        },
                        ordered_photo_ids,
                    )
                    created.append(serialize_page(page))

            album.status = AlbumStatus.PLANNED
            album.content_revision += 1
            await self.task_service.complete_success(
                task_id,
                result_payload={"page_count": len(created), "chapter_count": len(chapters)},
                debug_payload=debug_payload,
                metrics_payload={
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "page_count": len(created),
                    "chapter_count": len(chapters),
                    "fallback_used": debug_payload.get("fallback_used", False),
                },
                result_revision=album.content_revision,
            )
            await self.session.commit()
            return {"pages": created}
        except RuntimeError as exc:
            code = "task_cancelled" if "cancelled" in str(exc) else "stale_task"
            await self.task_service.complete_failure(
                task_id,
                error_code=code,
                error_message=str(exc),
                retryable=False,
                debug_payload={"stage": "persisting_pages", "reason": str(exc)},
            )
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="plan_failed",
                error_message=str(exc)[:500],
                retryable=False,
                debug_payload={
                    "stage": "persisting_pages",
                    "reason": str(exc)[:255],
                    "exception_type": exc.__class__.__name__,
                },
            )
            await self.session.commit()
            return None

    async def request_render_layout(self, album_id: str, user_id: str | None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=RENDER_TASK_TYPE,
            task_params=None,
            idempotency_key=f"render:{album_id}:{album.content_revision}",
            requested_revision=album.content_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=RENDER_JOB_NAME,
            pipeline_name=RENDER_PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            max_attempts=get_settings().queue_max_attempts,
        )

    async def _execute_spread_render(self, task_id: str, album, pages: list[Any], started: float):
        previous_manifest = await self.render_artifacts.load_manifest(album) or {}
        await self.runtime.heartbeat_step(task_id, "building_print_assets", 25)
        photos = [photo for photo in await self.photo_repo.list_photos(album.id) if is_photo_included(photo)]
        photos_by_id = {photo.id: photo for photo in photos}
        preview_sources = self._build_preview_photo_sources(photos_by_id)
        print_spec = self._default_print_spec(album)
        style_key = self._album_style_key(album)
        next_render_revision = album.render_revision + 1
        width_mm, height_mm = (254.0, 254.0) if album.book_size == "square_10inch" else (210.0, 297.0)
        spreads = await self.spread_repo.list_spreads(album.id)
        pages_by_spread = {spread.id: sorted(spread.pages, key=lambda page: 0 if page.side == "left" else 1) for spread in spreads}
        spread_pages = [page for pages_for_spread in pages_by_spread.values() for page in pages_for_spread]
        asset_targets = self._print_asset_targets(spread_pages, book_size=album.book_size)
        cover_photo = max(photos, key=lambda item: (item.quality_score or 0, (item.width or 0) * (item.height or 0))) if photos else None
        if cover_photo is not None:
            asset_targets[str(cover_photo.id)] = max(asset_targets.get(str(cover_photo.id), 0.0), min(width_mm, height_mm) - 32.0)
        print_sources, asset_keys, asset_failures = await self.print_assets.build_assets(
            album.id,
            next_render_revision,
            photos,
            page_dpi=int(print_spec.get("page_dpi", 300)),
            trim_edge_mm=max(width_mm, height_mm),
            slot_edge_mm_by_photo=asset_targets,
        )
        chapters = await self.chapter_repo.list_chapters(album.id)
        chapters_by_id = {chapter.id: chapter for chapter in chapters}

        preview_cover = self._page_photo_payloads([cover_photo], preview_sources)[0] if cover_photo else None
        print_cover = self._page_photo_payloads([cover_photo], print_sources)[0] if cover_photo else None
        preview_parts = [
            generate_cover_html(
                album.name,
                album.cover_title,
                style_key=style_key,
                style_presets=STYLE_PRESETS,
                print_spec=print_spec,
                chapter_count=len(chapters),
                photo_count=len(photos),
                cover_photo=preview_cover,
            ),
            generate_blank_page_html(style_key=style_key, style_presets=STYLE_PRESETS, print_spec=print_spec),
        ]
        print_parts = [
            generate_cover_html(
                album.name,
                album.cover_title,
                style_key=style_key,
                style_presets=STYLE_PRESETS,
                print_spec=print_spec,
                chapter_count=len(chapters),
                photo_count=len(photos),
                cover_photo=print_cover,
            ),
            generate_blank_page_html(style_key=style_key, style_presets=STYLE_PRESETS, print_spec=print_spec),
        ]
        blank_page_count = 1
        numbered_page_count = 0

        chapter_order = {chapter.id: index for index, chapter in enumerate(chapters, start=1)}
        chapter_groups: list[tuple[str | None, list[Any]]] = []
        for spread in spreads:
            if not chapter_groups or chapter_groups[-1][0] != spread.chapter_id:
                chapter_groups.append((spread.chapter_id, []))
            chapter_groups[-1][1].append(spread)

        await self.runtime.ensure_task_not_cancelled(task_id)
        await self.runtime.heartbeat_step(task_id, "rendering_spreads", 55)
        for chapter_id, grouped_spreads in chapter_groups:
            chapter = chapters_by_id.get(chapter_id) if chapter_id else None
            if chapter is not None:
                if (len(preview_parts) + 1) % 2 == 0:
                    blank = generate_blank_page_html(style_key=style_key, style_presets=STYLE_PRESETS, print_spec=print_spec)
                    preview_parts.append(blank)
                    print_parts.append(blank)
                    blank_page_count += 1
                divider = generate_chapter_divider_html(
                    chapter.name,
                    chapter.description,
                    chapter_index=chapter_order[chapter.id],
                    photo_count=sum(len(page.photo_links) for spread in grouped_spreads for page in spread.pages),
                    page_count=len(grouped_spreads) * 2,
                    style_key=style_key,
                    style_presets=STYLE_PRESETS,
                    print_spec=print_spec,
                )
                preview_parts.append(divider)
                print_parts.append(divider)
            if (len(preview_parts) + 1) % 2 == 1:
                blank = generate_blank_page_html(style_key=style_key, style_presets=STYLE_PRESETS, print_spec=print_spec)
                preview_parts.append(blank)
                print_parts.append(blank)
                blank_page_count += 1

            for spread in grouped_spreads:
                for page in pages_by_spread[spread.id]:
                    physical_number = len(preview_parts) + 1
                    expected_side = "left" if physical_number % 2 == 0 else "right"
                    if page.side != expected_side:
                        blank = generate_blank_page_html(style_key=style_key, style_presets=STYLE_PRESETS, print_spec=print_spec)
                        preview_parts.append(blank)
                        print_parts.append(blank)
                        blank_page_count += 1
                        physical_number += 1
                    page.physical_page_number = physical_number
                    page.display_page_number = physical_number
                    numbered_page_count += 1
                    template = LAYOUT_TEMPLATES.get(page.template, LAYOUT_TEMPLATES["grid_3"])
                    template_info = {"template": page.template, "css_class": template["css_class"], "slots": template["slots"]}
                    page_meta = dict(page.meta_json or {})
                    page_meta.update(
                        {
                            "layout_version": "spread_v2",
                            "style_key": style_key,
                            "side": page.side,
                            "headline": spread.headline,
                            "body": spread.body,
                            "text_side": (spread.meta_json or {}).get("text_side", "none"),
                            "display_page_number": physical_number,
                        }
                    )
                    preview_html = generate_layout_html(
                        template_info,
                        self._spread_page_photo_payloads(page, preview_sources),
                        physical_number,
                        page_meta=page_meta,
                        style_presets=STYLE_PRESETS,
                        print_spec=print_spec,
                    )
                    print_html = generate_layout_html(
                        template_info,
                        self._spread_page_photo_payloads(page, print_sources),
                        physical_number,
                        page_meta=page_meta,
                        style_presets=STYLE_PRESETS,
                        print_spec=print_spec,
                    )
                    await self.page_repo.update_page(
                        page,
                        {
                            "html": preview_html,
                            "status": "rendered",
                            "physical_page_number": physical_number,
                            "display_page_number": physical_number,
                            "meta_json": page_meta,
                        },
                        None,
                    )
                    preview_parts.append(preview_html)
                    print_parts.append(print_html)

        closer = generate_album_closer_html(
            album.name,
            style_key=style_key,
            style_presets=STYLE_PRESETS,
            print_spec=print_spec,
            photo_count=len(photos),
            chapter_count=len(chapters),
            page_count=numbered_page_count,
        )
        preview_parts.append(closer)
        print_parts.append(closer)
        if len(preview_parts) % 2:
            blank = generate_blank_page_html(style_key=style_key, style_presets=STYLE_PRESETS, print_spec=print_spec)
            preview_parts.append(blank)
            print_parts.append(blank)
            blank_page_count += 1

        preview_document = self._build_album_document(album.name, preview_parts)
        print_document = self._build_album_document(album.name, print_parts)
        manifest = self.render_artifacts.build_render_manifest(
            album,
            preview_html=preview_document,
            print_html=print_document,
            render_revision=next_render_revision,
            page_count=len(preview_parts),
            chapter_count=len(chapters),
            asset_mode="bounded_jpeg_derivatives",
            warnings=["Some print derivatives could not be generated."] if asset_failures else [],
            extra_stats={
                "print_asset_count": len(asset_keys),
                "print_asset_failure_count": len(asset_failures),
            },
            extra_fields={
                "layout_version": "spread_v2",
                "pdf_page_count": len(preview_parts),
                "numbered_page_count": numbered_page_count,
                "spread_count": len(spreads),
                "blank_page_count": blank_page_count,
                "print_assets": asset_keys,
                "print_asset_failures": asset_failures,
            },
        )
        await self.runtime.heartbeat_step(task_id, "persisting_render_artifacts", 85)
        previous_keys = self.render_artifacts.current_artifact_keys(album)
        preview_path, print_path, manifest_path = await self._persist_render_artifacts(
            album, preview_document, print_document, manifest
        )
        album.preview_html_path = preview_path
        album.print_html_path = print_path
        album.render_manifest_path = manifest_path
        album.status = AlbumStatus.RENDERED
        album.render_revision = next_render_revision
        stale_asset_keys = set((previous_manifest.get("print_assets") or {}).values()) - set(asset_keys.values())
        await self.render_artifacts.prune_replaced_render_artifacts(
            *previous_keys,
            *stale_asset_keys,
        )
        metrics = {
            "duration_ms": round((perf_counter() - started) * 1000),
            "pdf_page_count": len(preview_parts),
            "spread_count": len(spreads),
            "blank_page_count": blank_page_count,
            "print_asset_count": len(asset_keys),
        }
        await self.task_service.complete_success(
            task_id,
            result_payload={**metrics, "render_revision": album.render_revision},
            debug_payload={"stage": "persisting_render_artifacts", "reason": "spread_render_succeeded"},
            metrics_payload=metrics,
            result_revision=album.render_revision,
        )
        await self.session.commit()
        return metrics

    async def execute_render_layout(self, task_id: str, album_id: str):
        started = perf_counter()
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.content_revision)
            await self.runtime.heartbeat_step(task_id, "loading_pages", 10)
            pages = await self.page_repo.list_pages(album_id)
            if not pages:
                await self.task_service.complete_failure(
                    task_id,
                    error_code="no_pages",
                    error_message="no pages to render",
                    debug_payload={"stage": "loading_pages", "reason": "no_pages"},
                )
                await self.session.commit()
                return None

            if getattr(album, "layout_version", "legacy_page_v1") == "spread_v2":
                return await self._execute_spread_render(task_id, album, pages, started)

            photos_by_id = {photo.id: photo for photo in await self.photo_repo.list_photos(album_id) if is_photo_included(photo)}
            preview_sources = self._build_preview_photo_sources(photos_by_id)
            embedded_sources, embed_failures = await self._build_embedded_photo_sources(photos_by_id)
            chapters = await self.chapter_repo.list_chapters(album_id)
            chapters_by_id = {chapter.id: chapter for chapter in chapters}
            chapter_pages_map: dict[str | None, list] = {}
            for page in sorted(pages, key=lambda item: item.page_number):
                chapter_pages_map.setdefault(page.chapter_id, []).append(page)

            print_spec = self._default_print_spec(album)
            preview_parts: list[str] = [
                generate_cover_html(
                    album.name,
                    album.cover_title,
                    style_key=self._album_style_key(album),
                    style_presets=STYLE_PRESETS,
                    print_spec=print_spec,
                    chapter_count=len(chapters),
                    photo_count=album.photo_count,
                )
            ]
            print_parts = list(preview_parts)

            rendered_page_count = 0
            await self.runtime.ensure_task_not_cancelled(task_id)
            await self.runtime.heartbeat_step(task_id, "rendering_pages", 45)
            for chapter_order, (chapter_id, grouped_pages) in enumerate(
                sorted(chapter_pages_map.items(), key=lambda item: item[1][0].page_number if item[1] else 0),
                start=1,
            ):
                if chapter_id and chapter_id in chapters_by_id:
                    chapter = chapters_by_id[chapter_id]
                    chapter_style = next(
                        (
                            (page.meta_json or {}).get("style_key")
                            for page in grouped_pages
                            if (page.meta_json or {}).get("style_key")
                        ),
                        self._album_style_key(album),
                    )
                    divider_html = generate_chapter_divider_html(
                        chapter.name,
                        chapter.description,
                        chapter_index=chapter_order,
                        photo_count=sum(
                            1
                            for link in chapter.photo_links
                            if link.__dict__.get("photo") is None or is_photo_included(link.__dict__["photo"])
                        ),
                        page_count=len(grouped_pages),
                        style_key=chapter_style,
                        style_presets=STYLE_PRESETS,
                        print_spec=print_spec,
                    )
                    preview_parts.append(divider_html)
                    print_parts.append(divider_html)

                for page in grouped_pages:
                    ordered_ids = [link.photo_id for link in sorted(page.photo_links, key=lambda item: item.order_index)]
                    page_photos = [photos_by_id[pid] for pid in ordered_ids if pid in photos_by_id]
                    if page_photos:
                        template = LAYOUT_TEMPLATES.get(page.template, LAYOUT_TEMPLATES["grid_3"])
                        template_info = {"template": page.template, "css_class": template["css_class"], "slots": template["slots"]}
                        page_meta = page.meta_json or {}
                        preview_html = generate_layout_html(
                            template_info,
                            self._page_photo_payloads(page_photos, preview_sources),
                            page.page_number,
                            page_meta=page_meta,
                            style_presets=STYLE_PRESETS,
                            print_spec=print_spec,
                        )
                        export_html = generate_layout_html(
                            template_info,
                            self._page_photo_payloads(page_photos, embedded_sources),
                            page.page_number,
                            page_meta=page_meta,
                            style_presets=STYLE_PRESETS,
                            print_spec=print_spec,
                        )
                    else:
                        preview_html = f'<div class="page"><div class="page-number">{page.page_number}</div></div>'
                        export_html = preview_html
                    await self.page_repo.update_page(page, {"html": preview_html, "status": "rendered"}, None)
                    preview_parts.append(preview_html)
                    print_parts.append(export_html)
                    rendered_page_count += 1

            closer_html = generate_album_closer_html(
                album.name,
                style_key=self._album_style_key(album),
                style_presets=STYLE_PRESETS,
                print_spec=print_spec,
                photo_count=album.photo_count,
                chapter_count=len(chapters),
                page_count=rendered_page_count,
            )
            preview_parts.append(closer_html)
            print_parts.append(closer_html)

            next_render_revision = album.render_revision + 1
            preview_document = self._build_album_document(album.name, preview_parts)
            print_document = self._build_album_document(album.name, print_parts)
            manifest = self.render_artifacts.build_render_manifest(
                album,
                preview_html=preview_document,
                print_html=print_document,
                render_revision=next_render_revision,
                page_count=rendered_page_count,
                chapter_count=len(chapters),
                asset_mode="signed_preview_url_embedded_export",
                warnings=[],
                extra_stats={
                    "embedded_photo_failure_count": len(embed_failures),
                    "embedded_photo_count": len(embedded_sources),
                    "preview_photo_reference_count": len(preview_sources),
                },
                extra_fields={
                    "embedded_photo_failures": embed_failures,
                },
            )
            await self.runtime.heartbeat_step(task_id, "persisting_render_artifacts", 85)
            previous_keys = self.render_artifacts.current_artifact_keys(album)
            preview_path, print_path, manifest_path = await self._persist_render_artifacts(album, preview_document, print_document, manifest)
            album.preview_html_path = preview_path
            album.print_html_path = print_path
            album.render_manifest_path = manifest_path
            album.status = AlbumStatus.RENDERED
            album.render_revision += 1
            await self.render_artifacts.prune_replaced_render_artifacts(*previous_keys)
            await self.task_service.complete_success(
                task_id,
                result_payload={"page_count": rendered_page_count, "render_revision": album.render_revision},
                debug_payload={
                    "stage": "persisting_render_artifacts",
                    "reason": "render_succeeded",
                    "embedded_photo_failures": embed_failures,
                    "embedded_photo_count": len(embedded_sources),
                },
                metrics_payload={
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "page_count": rendered_page_count,
                    "embedded_photo_failure_count": len(embed_failures),
                },
                result_revision=album.render_revision,
            )
            await self.session.commit()
            return {"page_count": rendered_page_count}
        except RuntimeError as exc:
            code = "task_cancelled" if "cancelled" in str(exc) else "stale_task"
            await self.task_service.complete_failure(
                task_id,
                error_code=code,
                error_message=str(exc),
                retryable=False,
                debug_payload={"stage": "persisting_render_artifacts", "reason": str(exc)},
            )
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="render_failed",
                error_message=str(exc)[:500],
                retryable=False,
                debug_payload={
                    "stage": "persisting_render_artifacts",
                    "reason": str(exc)[:255],
                    "exception_type": exc.__class__.__name__,
                },
            )
            await self.session.commit()
            return None

    async def plan_pages(self, album_id: str):
        return await self.request_plan_pages(album_id, None)

    async def render_layout(self, album_id: str):
        return await self.request_render_layout(album_id, None)
