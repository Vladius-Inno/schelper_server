from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User, Task, Subtask, TASK_STATUS_VALUES
from ..schemas import HomeworkImportRequest, TaskCreate, TaskResponse, TaskUpdate, TaskOut, SubtaskCreate, SubtaskUpdate, SubtaskOut, StatusResponse, JobOut, JobCreate
from app.routers.jobs import create_job


router = APIRouter(prefix="/import", tags=["import"])


@router.post("/homework", response_model=JobOut)
async def import_homework(payload: HomeworkImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Ставит задачу на импорт домашнего задания в очередь.
    Возвращает job_id для отслеживания статуса.
    """
    # --- child_id по аналогии с tasks ---
    child_id = payload.child_id
    if user.role == "child":
        child_id = user.id
    elif child_id is None:
        child_id = user.id
    elif user.role != "admin":
        child_id = user.id

    payload = {
        "text": payload.text,
        "child_id": payload.child_id,
    }

    job_in = JobCreate(
        type="import_homework",
        payload=payload,
    )

    job = await create_job(job_in, db, user)
    return job
