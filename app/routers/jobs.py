from __future__ import annotations
import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Query, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User, Job
from ..schemas import JobCreate, JobOut, JobUpdate

# --- Публичный роутер для пользователя ---
router = APIRouter(prefix="/jobs", tags=["jobs"])

# загрузим переменные из .env
load_dotenv()


@router.get("/", response_model=List[JobOut])
async def list_jobs(
    status: Optional[str] = Query(default=None),
    job_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Job).where(Job.user_id == user.id)
    if status:
        q = q.where(Job.status == status)
    if job_type:
        q = q.where(Job.type == job_type)

    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=JobOut)
async def create_job(
    payload: JobCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    new_job = Job(
        user_id=user.id,
        type=payload.type,
        status="pending",
        payload=payload.payload,   # 👈 если в схеме есть

    )
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    return new_job


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Job).where(Job.id == job_id, Job.user_id == user.id)
    result = await db.execute(q)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}", response_model=JobOut)
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Job).where(Job.id == job_id, Job.user_id == user.id)
    result = await db.execute(q)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.delete(job)
    await db.commit()
    return job


# --- Внутренний роутер для воркеров ---
internal_router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"])


def verify_worker(x_api_key: str = Header(...)):
    # 👇 Здесь лучше вынести в настройки (например, через ENV)
    WORKER_API_KEY = os.environ.get("WORKER_API_KEY")

    if x_api_key != WORKER_API_KEY:
        raise HTTPException(status_code=403, detail="Not authorized")
    return True


@internal_router.patch("/{job_id}", response_model=JobOut)
async def update_job_status(
    job_id: str,
    payload: JobUpdate,
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(verify_worker),  # 👈 проверка API-ключа
):
    q = select(Job).where(Job.id == job_id)
    result = await db.execute(q)
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    data = payload.dict(exclude_unset=True)

    if "status" in data:
        job.status = data["status"]
    if "payload" in data:
        job.payload = data["payload"]
    if "result" in data:
        job.result = data["result"]

    await db.commit()
    await db.refresh(job)
    return job
