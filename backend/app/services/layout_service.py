from __future__ import annotations

import base64
import mimetypes
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.core.config import get_settings
from app.engines.layout_engine.prompt_pipeline import recommend_layout_with_ai
from app.engines.layout_engine.service import (
    CSS_STYLES,
    LAYOUT_TEMPLATES,
    generate_album_closer_html,
    generate_chapter_divider_html,
    generate_cover_html,
    generate_layout_html,
    plan_pages,
)
from app.engines.layout_engine.templates import STYLE_PRESETS, build_template_catalog
from app.repositories.album_repo import AlbumRepository
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.page_repo import PageRepository
from app.repositories.photo_repo import PhotoRepository
from app.repositories.task_repo import TaskRepository
from app.services.project_ai_config_service import ProjectAIConfigService
from app.services.render_artifact_service import RenderArtifactService, clear_render_artifacts
from app.services.serializers import serialize_page
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
        self.task_repo = TaskRepository(session)
        self.storage = get_file_storage()
        self.ai_config_service = ProjectAIConfigService(session)
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.render_artifacts = RenderArtifactService()

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
            "color_profile": "rgb",
        }

    @staticmethod
    def _album_style_key(album) -> str:
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

    async def request_plan_pages(self, album_id: str, user_id: str | None) -> dict | None:
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
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
            keep_photos = [photo for photo in photos if photo.cleaning_recommendation != "remove"]
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

            photos_by_id = {photo.id: photo for photo in await self.photo_repo.list_photos(album_id)}
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
                        photo_count=len(chapter.photo_links),
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
