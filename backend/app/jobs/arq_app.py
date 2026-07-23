from __future__ import annotations

from arq.connections import RedisSettings, create_pool

from app.core.config import get_settings
from app.core.observability import configure_observability, configure_sentry
from app.jobs.handlers import (
    run_cleaning_job,
    run_cluster_chapters_job,
    run_export_job,
    run_plan_pages_job,
    run_render_layout_job,
    run_theme_analysis_job,
    run_theme_selection_job,
)
from app.services.task_dispatch_service import TaskDispatchService
from app.services.task_service import TaskService
from app.db import session as db_session
from app.engines.export_engine.service import close_shared_browser


def build_redis_settings() -> RedisSettings:
    settings = get_settings()
    return RedisSettings.from_dsn(settings.redis_url)


async def get_arq_pool():
    return await create_pool(build_redis_settings())


async def on_startup(ctx):  # noqa: ANN001
    settings = get_settings()
    configure_observability(service_name="worker", log_level=settings.observability_log_level, json_logs=settings.observability_json_logs)
    configure_sentry(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        service_name="worker",
    )
    async with db_session.AsyncSessionFactory() as session:
        await TaskService(session).recover_stale_running_tasks()
        await TaskDispatchService(session).flush_pending_dispatches(settings.task_dispatch_batch_size)


async def on_shutdown(ctx):  # noqa: ANN001
    await close_shared_browser()


class WorkerSettings:
    functions = [
        run_cleaning_job,
        run_theme_analysis_job,
        run_theme_selection_job,
        run_cluster_chapters_job,
        run_plan_pages_job,
        run_render_layout_job,
        run_export_job,
    ]
    redis_settings = build_redis_settings()
    max_jobs = get_settings().queue_worker_concurrency
    job_timeout = get_settings().queue_job_timeout_seconds
    on_startup = on_startup
    on_shutdown = on_shutdown
