from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import AlbumStatus
from app.engines.export_engine.service import PdfExportError, _safe_export_name, export_to_pdf
from app.repositories.album_repo import AlbumRepository
from app.repositories.export_repo import ExportRepository
from app.repositories.task_repo import TaskRepository
from app.services.render_artifact_service import RenderArtifactService
from app.services.task_runtime_service import TaskRuntimeService
from app.services.task_service import TaskService
from app.storage.file_store import get_file_storage

PIPELINE_NAME = "export"
PIPELINE_VERSION = "p0-async-v1"
JOB_NAME = "run_export_job"
EXPORTABLE_STATUSES = {AlbumStatus.RENDERED, AlbumStatus.EXPORTED}


def _peak_memory_mb() -> float | None:
    try:
        import resource

        peak = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux reports KiB while macOS reports bytes.
        return round(peak / (1024 * 1024 if os.name == "posix" and peak > 1024 * 1024 else 1024), 2)
    except (ImportError, AttributeError):
        return None


class ExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.album_repo = AlbumRepository(session)
        self.export_repo = ExportRepository(session)
        self.task_repo = TaskRepository(session)
        self.storage = get_file_storage()
        self.task_service = TaskService(session)
        self.runtime = TaskRuntimeService(self.task_service)
        self.render_artifacts = RenderArtifactService()

    @staticmethod
    def _profile_hash(album, export_format: str) -> str:
        profile = {
            "format": export_format,
            "render_revision": album.render_revision,
            "book_size": album.book_size,
            "print_spec": album.print_spec_json or {},
        }
        encoded = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _export_payload(export) -> dict:
        return {
            "id": export.id,
            "album_id": export.album_id,
            "status": export.status,
            "format": export.format,
            "file_path": export.file_path,
            "file_size": export.file_size,
            "render_revision": export.render_revision,
            "profile_hash": export.profile_hash,
        }

    async def _complete_export_failure(
        self,
        task_id: str,
        *,
        error_code: str,
        error_message: str,
        export_format: str,
        stage: str,
        started: float,
        exc: Exception | None = None,
        retryable: bool = False,
    ) -> None:
        reason = str(exc)[:500] if exc else None
        debug_payload = {
            "format": export_format,
            "stage": stage,
            "reason": reason,
            "exception_type": exc.__class__.__name__ if exc else None,
        }
        await self.task_service.complete_failure(
            task_id,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            debug_payload=debug_payload,
            metrics_payload={
                "format": export_format,
                "stage": stage,
                "duration_ms": round((perf_counter() - started) * 1000),
            },
        )
        await self.session.commit()

    async def request_export_album(self, album_id: str, user_id: str | None, format: str = "html") -> dict | None:  # noqa: A002
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        if album.status not in EXPORTABLE_STATUSES:
            return None
        html_content = await self.render_artifacts.load_print_html(album)
        if not html_content:
            return None
        profile_hash = self._profile_hash(album, format)
        cached = await self.export_repo.find_completed(
            album_id,
            format=format,
            render_revision=album.render_revision,
            profile_hash=profile_hash,
        )
        if cached is not None and cached.file_path:
            try:
                await self.storage.open_file(cached.file_path)
                return {"cache_hit": True, "export": self._export_payload(cached)}
            except FileNotFoundError:
                pass
        return await self.task_service.request_task(
            album_id=album_id,
            user_id=user_id,
            task_type=f"export_{format}",
            task_params={"format": format, "profile_hash": profile_hash},
            idempotency_key=f"export:{album_id}:{format}:{album.render_revision}:{profile_hash}",
            requested_revision=album.render_revision,
            resource_type="album",
            resource_id=album_id,
            job_name=JOB_NAME,
            pipeline_name=PIPELINE_NAME,
            pipeline_version=PIPELINE_VERSION,
            max_attempts=3,
        )

    async def execute_export(self, task_id: str, album_id: str, format: str = "html"):  # noqa: A002
        started = perf_counter()
        phase_metrics: dict[str, object] = {}
        album = await self.album_repo.get_album(album_id)
        if album is None:
            await self.task_service.complete_failure(task_id, error_code="album_not_found", error_message="album not found")
            return None
        try:
            await self.runtime.ensure_revision_matches(task_id, album.render_revision)
            await self.runtime.heartbeat_step(task_id, "loading_render_artifacts", 10)
            if album.status not in EXPORTABLE_STATUSES:
                await self.task_service.complete_failure(
                    task_id,
                    error_code="not_rendered",
                    error_message="album not rendered",
                    debug_payload={"stage": "loading_render_artifacts", "reason": "album_not_rendered"},
                )
                await self.session.commit()
                return None
            phase_started = perf_counter()
            html_content = await self.render_artifacts.load_print_html(album)
            phase_metrics["resource_read_ms"] = round((perf_counter() - phase_started) * 1000)
            if not html_content:
                await self.task_service.complete_failure(
                    task_id,
                    error_code="missing_html",
                    error_message="render output missing",
                    debug_payload={"stage": "loading_render_artifacts", "reason": "render_output_missing"},
                )
                await self.session.commit()
                return None

            export_id = str(uuid4())
            print_spec = album.print_spec_json or {"book_size": album.book_size, "bleed_mm": 3, "safe_margin_mm": 8}
            profile_hash = self._profile_hash(album, format)
            warnings: list[str] = []
            await self.runtime.ensure_task_not_cancelled(task_id)
            if format == "pdf":
                await self.runtime.heartbeat_step(task_id, "pdf_generate", 50)
                try:
                    phase_started = perf_counter()
                    manifest = await self.render_artifacts.load_manifest(album) or {}
                    with TemporaryDirectory(prefix="pixelpress-export-") as temp_dir:
                        asset_started = perf_counter()
                        replacements = await self.render_artifacts.materialize_print_assets(
                            manifest, Path(temp_dir) / "assets"
                        )
                        phase_metrics["asset_materialize_ms"] = round((perf_counter() - asset_started) * 1000)
                        materialized_html = self.render_artifacts.rewrite_html_sources(html_content, replacements)
                        raw_result = await export_to_pdf(
                            materialized_html,
                            album.name or "album",
                            export_id,
                            album.book_size,
                            print_spec,
                        )
                    expected_page_count = manifest.get("pdf_page_count")
                    actual_page_count = len(PdfReader(raw_result["file_path"]).pages)
                    raw_result["pdf_page_count"] = actual_page_count
                    if expected_page_count is not None and int(expected_page_count) != actual_page_count:
                        raise PdfExportError(
                            f"PDF page count mismatch: expected {expected_page_count}, got {actual_page_count}"
                        )
                    phase_metrics["pdf_write_ms"] = round((perf_counter() - phase_started) * 1000)
                    phase_metrics["pdf_page_count"] = actual_page_count
                    for metric, value in (raw_result.get("metrics") or {}).items():
                        phase_metrics[f"pdf_{metric}"] = value
                except PdfExportError as exc:
                    await self._complete_export_failure(
                        task_id,
                        error_code="pdf_export_failed",
                        error_message="PDF 导出失败",
                        export_format="pdf",
                        stage="pdf_generate",
                        started=started,
                        exc=exc,
                    )
                    return None

                output_path = Path(raw_result["file_path"])
                try:
                    phase_started = perf_counter()
                    stored = await self.storage.save_export_from_path(
                        album_id,
                        output_path.name,
                        output_path,
                        "application/pdf",
                    )
                    phase_metrics["storage_upload_ms"] = round((perf_counter() - phase_started) * 1000)
                except Exception as exc:  # noqa: BLE001
                    await self._complete_export_failure(
                        task_id,
                        error_code="pdf_export_failed",
                        error_message="PDF 导出失败",
                        export_format="pdf",
                        stage="pdf_store",
                        started=started,
                        exc=exc,
                    )
                    return None
                finally:
                    if output_path.exists():
                        output_path.unlink()
                export_format = "pdf"
                warnings = raw_result.get("warnings", [])
            else:
                safe_name = _safe_export_name(album.name or "album")
                export_name = f"{safe_name}_{export_id[:8]}.html"
                file_bytes = html_content.encode("utf-8")
                stored = await self.storage.save_export(album_id, export_name, file_bytes, "text/html")
                export_format = "html"

            export = await self.export_repo.create_export(
                {
                    "album_id": album_id,
                    "task_id": task_id,
                    "format": export_format,
                    "status": "completed",
                    "file_path": stored.storage_key,
                    "file_size": stored.size,
                    "render_revision": album.render_revision,
                    "profile_hash": profile_hash,
                }
            )
            album.status = AlbumStatus.EXPORTED
            await self.task_service.complete_success(
                task_id,
                result_payload={"export_id": export.id, "format": export_format, "warnings": warnings},
                debug_payload={"stage": "pdf_store" if export_format == "pdf" else "html_store", "reason": "export_succeeded", "format": export_format},
                metrics_payload={
                    "duration_ms": round((perf_counter() - started) * 1000),
                    "format": export_format,
                    "cache_hit": False,
                    **phase_metrics,
                    **({"peak_memory_mb": _peak_memory_mb()} if _peak_memory_mb() is not None else {}),
                },
                result_revision=album.render_revision,
            )
            await self.session.commit()
            return {
                "export_id": export.id,
                "format": export_format,
                "warnings": warnings,
                "cache_hit": False,
                "export": self._export_payload(export),
            }
        except RuntimeError as exc:
            code = "task_cancelled" if "cancelled" in str(exc) else "stale_task"
            await self.task_service.complete_failure(
                task_id,
                error_code=code,
                error_message=str(exc),
                retryable=False,
                debug_payload={"stage": "pdf_store" if format == "pdf" else "html_store", "reason": str(exc)},
            )
            await self.session.commit()
            return None
        except Exception as exc:  # noqa: BLE001
            await self.task_service.complete_failure(
                task_id,
                error_code="export_failed",
                error_message=str(exc)[:500],
                retryable=False,
                debug_payload={
                    "stage": "pdf_store" if format == "pdf" else "html_store",
                    "reason": str(exc)[:255],
                    "exception_type": exc.__class__.__name__,
                },
            )
            await self.session.commit()
            return None

    async def export_album(self, album_id: str, format: str = "html"):  # noqa: A002
        return await self.request_export_album(album_id, None, format)

    async def download_export(self, album_id: str, export_id: str):
        export = await self.export_repo.get_export(album_id, export_id)
        if export is None:
            return None
        return export

    async def open_export_content(self, album_id: str, export_id: str):
        export = await self.export_repo.get_export(album_id, export_id)
        if export is None or not export.file_path:
            return None
        content = await self.storage.open_file(export.file_path)
        return export, content

    async def list_exports(self, album_id: str):
        album = await self.album_repo.get_album(album_id)
        if album is None:
            return None
        exports = await self.export_repo.list_exports(album_id)
        return [
            {
                "id": item.id,
                "album_id": item.album_id,
                "status": item.status,
                "format": item.format,
                "file_path": item.file_path,
                "file_size": item.file_size,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "task_id": item.task_id,
            }
            for item in exports
        ]
