from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.common.enums import AlbumStatus
from app.services.render_access_service import RenderAccessService
from app.storage.file_store import get_file_storage

logger = logging.getLogger(__name__)
PREVIEW_TOKEN_TTL_SECONDS = 300


class _PreviewHtmlRewriter(HTMLParser):
    def __init__(self, replacements: dict[str, str]) -> None:
        super().__init__(convert_charrefs=False)
        self.replacements = replacements
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._render_tag(tag, attrs, closed=False))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self._render_tag(tag, attrs, closed=True))

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_comment(self, data: str) -> None:
        self.parts.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")

    def output(self) -> str:
        return "".join(self.parts)

    def _render_tag(self, tag: str, attrs: list[tuple[str, str | None]], *, closed: bool) -> str:
        rendered_attrs: list[str] = []
        for key, value in attrs:
            if tag == "img" and key == "src" and value in self.replacements:
                value = self.replacements[value]
            if value is None:
                rendered_attrs.append(key)
            else:
                escaped = value.replace('"', '&quot;')
                rendered_attrs.append(f'{key}="{escaped}"')
        suffix = " />" if closed else ">"
        if rendered_attrs:
            return f"<{tag} {' '.join(rendered_attrs)}{suffix}"
        return f"<{tag}{suffix}"


class RenderArtifactService:
    def __init__(self) -> None:
        self.storage = get_file_storage()
        self.render_access = RenderAccessService()

    @staticmethod
    def current_artifact_keys(album) -> tuple[str | None, str | None, str | None]:
        return (
            getattr(album, "preview_html_path", None),
            getattr(album, "print_html_path", None),
            getattr(album, "render_manifest_path", None),
        )

    @staticmethod
    def artifact_file_name(render_revision: int, file_name: str) -> str:
        return f"r{render_revision}/{file_name}"

    @staticmethod
    def artifact_storage_key(album_id: str, artifact_name: str) -> str:
        return f"albums/{album_id}/artifacts/{artifact_name}"

    def build_render_manifest(
        self,
        album,
        *,
        preview_html: str,
        print_html: str,
        render_revision: int,
        page_count: int,
        chapter_count: int,
        asset_mode: str,
        warnings: list[str] | None = None,
        extra_stats: dict[str, Any] | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        preview_name = self.artifact_file_name(render_revision, "preview.html")
        print_name = self.artifact_file_name(render_revision, "print.html")
        manifest_name = self.artifact_file_name(render_revision, "manifest.json")
        manifest: dict[str, Any] = {
            "album_id": album.id,
            "render_revision": render_revision,
            "content_revision": album.content_revision,
            "preview_html_path": self.artifact_storage_key(album.id, preview_name),
            "print_html_path": self.artifact_storage_key(album.id, print_name),
            "render_manifest_path": self.artifact_storage_key(album.id, manifest_name),
            "page_count": page_count,
            "chapter_count": chapter_count,
            "asset_mode": asset_mode,
            "warnings": warnings or [],
            "generated_at": datetime.now(UTC).isoformat(),
            "stats": {
                "html_bytes": len(preview_html.encode("utf-8")),
                "preview_html_bytes": len(preview_html.encode("utf-8")),
                "print_html_bytes": len(print_html.encode("utf-8")),
            },
        }
        if extra_stats:
            manifest["stats"].update(extra_stats)
        if extra_fields:
            manifest.update(extra_fields)
        return manifest

    async def persist_render_bundle(
        self,
        album,
        preview_html: str,
        print_html: str,
        manifest: dict[str, Any],
    ) -> tuple[str, str, str]:
        render_revision = int(manifest["render_revision"])
        preview_file = await self.storage.save_artifact(
            album.id,
            self.artifact_file_name(render_revision, "preview.html"),
            preview_html.encode("utf-8"),
            "text/html",
        )
        print_file = await self.storage.save_artifact(
            album.id,
            self.artifact_file_name(render_revision, "print.html"),
            print_html.encode("utf-8"),
            "text/html",
        )
        manifest_file = await self.storage.save_artifact(
            album.id,
            self.artifact_file_name(render_revision, "manifest.json"),
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            "application/json",
        )
        return preview_file.storage_key, print_file.storage_key, manifest_file.storage_key

    async def load_preview_html(self, album) -> str | None:
        html = await self._load_html(album, path_attr="preview_html_path", artifact_kind="preview")
        if not html:
            return None
        return self._rewrite_preview_html(album, html)

    async def load_print_html(self, album) -> str | None:
        return await self._load_html(album, path_attr="print_html_path", artifact_kind="print")

    async def load_manifest(self, album) -> dict[str, Any] | None:
        storage_key = getattr(album, "render_manifest_path", None)
        if not storage_key:
            return None
        try:
            return json.loads((await self.storage.open_file(storage_key)).decode("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    async def materialize_print_assets(self, manifest: dict[str, Any], target_dir: Path) -> dict[str, str]:
        replacements: dict[str, str] = {}
        target_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(8)

        async def materialize(photo_id: str, storage_key: str) -> tuple[str, str]:
            target = target_dir / f"{photo_id}.jpg"
            async with semaphore:
                await self.storage.copy_to_path(str(storage_key), target)
            return photo_id, target.as_uri()

        completed = await asyncio.gather(
            *(materialize(str(photo_id), str(storage_key)) for photo_id, storage_key in (manifest.get("print_assets") or {}).items())
        )
        for photo_id, local_uri in completed:
            replacements[f"pixpress-asset://{photo_id}"] = local_uri
        return replacements

    @staticmethod
    def rewrite_html_sources(html: str, replacements: dict[str, str]) -> str:
        if not replacements:
            return html
        parser = _PreviewHtmlRewriter(replacements)
        parser.feed(html)
        parser.close()
        return parser.output()

    async def delete_render_artifacts(self, *storage_keys: str | None) -> None:
        for storage_key in storage_keys:
            if not storage_key:
                continue
            try:
                await self.storage.delete_file(storage_key)
            except FileNotFoundError:
                continue

    async def prune_replaced_render_artifacts(self, *storage_keys: str | None) -> None:
        await self.delete_render_artifacts(*storage_keys)

    async def _load_html(self, album, *, path_attr: str, artifact_kind: str) -> str | None:
        storage_key = getattr(album, path_attr, None)
        if storage_key:
            try:
                return (await self.storage.open_file(storage_key)).decode("utf-8")
            except FileNotFoundError:
                logger.warning(
                    "Missing %s render artifact for album %s at %s",
                    artifact_kind,
                    getattr(album, "id", "unknown"),
                    storage_key,
                )
        legacy_html = getattr(album, "full_html", None)
        if legacy_html:
            logger.warning(
                "Falling back to legacy full_html for %s render artifact on album %s",
                artifact_kind,
                getattr(album, "id", "unknown"),
            )
            return legacy_html
        return None

    def _rewrite_preview_html(self, album, html: str) -> str:
        replacements: dict[str, str] = {}
        for photo in getattr(album, "photos", []) or []:
            original_url = getattr(photo, "url", None)
            if not original_url:
                continue
            replacements[original_url] = self.render_access.build_photo_preview_url(
                album_id=album.id,
                photo_id=photo.id,
                render_revision=album.render_revision,
                ttl_seconds=PREVIEW_TOKEN_TTL_SECONDS,
            )
        if not replacements:
            return html
        parser = _PreviewHtmlRewriter(replacements)
        parser.feed(html)
        parser.close()
        return parser.output()


async def clear_render_artifacts(album, render_artifacts: RenderArtifactService, *, stale_status: str | None = None) -> None:
    keys = render_artifacts.current_artifact_keys(album)
    # Print assets are content-addressed by photo and print profile. Keep them
    # when only copy, crop, or visual style changes so the next render skips
    # image decoding and JPEG encoding.
    await render_artifacts.prune_replaced_render_artifacts(*keys)
    album.preview_html_path = None
    album.print_html_path = None
    album.render_manifest_path = None
    album.full_html = None
    if stale_status and album.status in {AlbumStatus.RENDERED, AlbumStatus.EXPORTED}:
        album.status = stale_status


def mark_render_artifacts_stale(album, *, stale_status: str | None = None) -> None:
    album.preview_html_path = None
    album.print_html_path = None
    album.render_manifest_path = None
    album.full_html = None
    if stale_status and album.status in {AlbumStatus.RENDERED, AlbumStatus.EXPORTED}:
        album.status = stale_status
