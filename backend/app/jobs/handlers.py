from __future__ import annotations

from app.core.observability import apply_sentry_context
from app.core.request_context import replace_request_context
from app.db import session as db_session
from app.services.chapter_clustering_task_runner import ChapterClusteringTaskRunner
from app.services.cleaning_service import CleaningService
from app.services.export_service import ExportService
from app.services.layout_service import LayoutService
from app.services.task_service import TaskService
from app.services.theme_curation_service import ThemeCurationService
from app.services.theme_curation_task_runner import ThemeCurationTaskRunner
from app.services.workflow_guard_service import WorkflowGuardService


def _bind_worker_context(*, task_id: str, album_id: str, request_id: str | None, worker_name: str, job_id: str | None = None) -> None:
    replace_request_context(
        request_id=request_id,
        task_id=task_id,
        album_id=album_id,
        worker_name=worker_name,
        job_id=job_id or task_id,
    )
    apply_sentry_context()


async def _claim_task(session, task_id: str, worker_name: str):
    task = await TaskService(session).claim_task(task_id, worker_name, job_id=task_id)
    if task is None:
        return None
    return task


async def run_cleaning_job(
    ctx,
    task_id: str,
    album_id: str,
    request_id: str | None = None,
    pipeline_version: str | None = None,
) -> None:  # noqa: ANN001
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-cleaning")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-cleaning") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await CleaningService(session).execute_cleaning(task_id, album_id, pipeline_version=pipeline_version)


async def run_cluster_chapters_job(
    ctx,
    task_id: str,
    album_id: str,
    request_id: str | None = None,
    confirm_rebuild: bool = False,
    granularity: int = 0,
) -> None:  # noqa: ANN001
    del confirm_rebuild, granularity
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-cluster")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-cluster") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await ChapterClusteringTaskRunner(session).execute(task_id, album_id)


async def run_theme_analysis_job(
    ctx,
    task_id: str,
    album_id: str,
    request_id: str | None = None,
    custom_theme: str | None = None,
) -> None:  # noqa: ANN001
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-theme-analysis")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-theme-analysis") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await ThemeCurationTaskRunner(session).execute_analysis(task_id, album_id, custom_theme=custom_theme)


async def run_theme_selection_job(
    ctx,
    task_id: str,
    album_id: str,
    request_id: str | None = None,
    profile_id: str = "",
    candidate_id: str = "",
    chapter_strategy: str = "balanced",
    confirm_rebuild: bool = False,
) -> None:  # noqa: ANN001
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-theme-selection")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-theme-selection") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await ThemeCurationTaskRunner(session).execute_selection(
            task_id,
            album_id,
            profile_id=profile_id,
            candidate_id=candidate_id,
            chapter_strategy=chapter_strategy,
            confirm_rebuild=confirm_rebuild,
        )


async def run_plan_pages_job(ctx, task_id: str, album_id: str, request_id: str | None = None) -> None:  # noqa: ANN001
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-plan")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-plan") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await LayoutService(session).execute_plan_pages(task_id, album_id)


async def run_render_layout_job(ctx, task_id: str, album_id: str, request_id: str | None = None) -> None:  # noqa: ANN001
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-render")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-render") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await LayoutService(session).execute_render_layout(task_id, album_id)


async def run_export_job(ctx, task_id: str, album_id: str, request_id: str | None = None, format: str = "html") -> None:  # noqa: ANN001,A002
    _bind_worker_context(task_id=task_id, album_id=album_id, request_id=request_id, worker_name="arq-export")
    async with db_session.AsyncSessionFactory() as session:
        if await _claim_task(session, task_id, "arq-export") is None:
            return
        await WorkflowGuardService(session).acquire_album_guard(album_id)
        await ExportService(session).execute_export(task_id, album_id, format)
