from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from tasks import create_task
from app.service.agent_parser import agent_parse_homework

from ..auth import get_current_user
from ..db import get_db
from ..models import User, Task, Subtask, TASK_STATUS_VALUES
from ..schemas import HomeworkImportRequest, TaskCreate, TaskUpdate, TaskOut, SubtaskCreate, SubtaskUpdate, SubtaskOut, StatusResponse


router = APIRouter(prefix="/import", tags=["import"])


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


@router.post("/homework", response_model=TaskOut)
async def import_homework(
    payload: HomeworkImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Принимает текст/файл/скриншот, вызывает ИИ-агента,
    создаёт Task + Subtasks.
    """
    # 1. получить текст
    if payload.text:
        raw_text = payload.text
    # elif payload.file_id:
    #     raw_text = await extract_text_from_file(payload.file_id)
    else:
        raise HTTPException(status_code=400, detail="No homework content provided")

    # 2. вызвать ИИ-агента
    ai_result = await agent_parse_homework(raw_text)

    # 3. собрать TaskCreate
    task_create = TaskCreate(
        child_id=payload.child_id,
        subject_id=payload.subject_id,
        date=payload.date or _today_str(),
        title=ai_result["title"],
        subtasks=[SubtaskCreate(title=st) for st in ai_result["subtasks"]]
    )

    # 4. использовать существующую create_task
    return await create_task(task_create, db, user)
