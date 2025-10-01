import asyncio
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db import async_session_maker
from app.models import Job
from app.schemas import JobStatus

from app.worker.process_import import process_import_homework
# в будущем можно подключать другие обработчики:
# from app.worker.process_summary import process_summary

logger = logging.getLogger(__name__)

# === РЕГИСТР ОБРАБОТЧИКОВ ===
JOB_HANDLERS = {
    "import_homework": process_import_homework,
    # "summary": process_summary,
    # "export": process_export,
}


async def worker_loop(poll_interval: int = 2):
    """Основной цикл воркера"""
    logger.info("Worker started...")

    while True:
        async with async_session_maker() as session:
            job = await _fetch_next_job(session)
            if job:
                await _process_job(session, job)
            else:
                await asyncio.sleep(poll_interval)


async def _fetch_next_job(session: AsyncSession):
    """Забираем первую pending-job"""
    q = (
        select(Job)
        .where(Job.status == JobStatus.PENDING)
        .order_by(Job.created_at.asc())
        .limit(1)
    )
    result = await session.execute(q)
    return result.scalars().first()


async def _process_job(session: AsyncSession, job: Job):
    """Обработка конкретной job"""
    handler = JOB_HANDLERS.get(job.type)
    if not handler:
        logger.error(f"No handler for job type {job.type}")
        await _update_status(session, job, JobStatus.FAILED, {"error": "Unknown job type"})
        return

    try:
        logger.info(f"Processing job {job.id} ({job.type})")

        # update → RUNNING
        await _update_status(session, job, JobStatus.RUNNING)

        # вызов обработчика
        result = await handler(session, job)

        # update → DONE
        await _update_status(session, job, JobStatus.DONE, {"result": result})

        logger.info(f"Job {job.id} completed")

    except Exception as e:
        logger.exception(f"Job {job.id} failed")
        await _update_status(session, job, JobStatus.FAILED, {"error": str(e)})


async def _update_status(session: AsyncSession, job: Job, status: JobStatus, meta: dict | None = None):
    job.status = status
    job.updated_at = datetime.utcnow()
    if meta:
        job.meta = meta
    await session.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop())
