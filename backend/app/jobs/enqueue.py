from __future__ import annotations

from app.jobs.arq_app import get_arq_pool


async def enqueue_job(*, job_name: str, job_id: str, payload: dict) -> None:
    redis = await get_arq_pool()
    await redis.enqueue_job(job_name, _job_id=job_id, **payload)
