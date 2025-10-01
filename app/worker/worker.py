import asyncio
import logging
from datetime import UTC, datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.db import AsyncSessionLocal  # ✅ используем фабрику из db.py
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
        async with AsyncSessionLocal() as session:  # ✅ правильная фабрика
            job = await _fetch_next_job(session)
            if job:
                await _process_job(session, job)
            else:
                await asyncio.sleep(poll_interval)


async def _fetch_next_job(session: AsyncSession):
    """Забираем первую pending-job"""
    result = await session.execute(
        select(
            Job.id,
            Job.user_id,
            Job.type,
            Job.status,
            Job.payload,
        )
        .where(Job.status == JobStatus.PENDING.value)
        .order_by(Job.created_at)
        .limit(1)
    )
    row = result.first()
    if not row:
        return None
    return dict(row._mapping)  # превращаем в dict, без ORM


async def _process_job(session: AsyncSession, job: Job):
    """Обработка конкретной job"""
    handler = JOB_HANDLERS.get(job["type"])
    if not handler:
        logger.error(f"No handler for job type {job["type"]}")
        await _update_status(session, job, JobStatus.FAILED.value, {"error": "Unknown job type"})
        return

    try:
        logger.info(f"Processing job {job["id"]} ({job["type"]})")

        # update → RUNNING
        await _update_status(session, job, JobStatus.RUNNING.value)

        # вызов обработчика
        result = await handler(session, job)

        # update → DONE
        await _update_status(session, job, JobStatus.DONE.value, {"result": result})

        logger.info(f"Job {job["id"]} completed")

    except Exception as e:
        logger.exception(f"Job {job["id"]} failed")
        await _update_status(session, job, JobStatus.FAILED.value, {"error": str(e)})


async def _update_status(session: AsyncSession, job: dict, status: JobStatus, result: dict | None = None):
    await session.execute(
        update(Job)
        .where(Job.id == job["id"])
        .values(
            status=status,
            result=result,
            updated_at=datetime.now(),
        )
    )
    await session.commit()



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop())
