from __future__ import annotations

from datetime import datetime
from typing import List, Optional
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User, Task, Subtask, TASK_STATUS_VALUES
from ..schemas import TaskCreate, TaskResponse, TaskUpdate, TaskOut, SubtaskCreate, SubtaskUpdate, SubtaskOut, StatusResponse


router = APIRouter(prefix="/tasks", tags=["tasks"])


def _today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def _parse_iso_date(value: str, field: str) -> datetime:
    """Validate ISO date (YYYY-MM-DD) and return datetime for comparisons."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid {}, expected YYYY-MM-DD".format(field)) from exc


def _compute_task_status(subtasks: list[Subtask]) -> str:
    if not subtasks:
        return "todo"
    statuses = {s.status for s in subtasks}
    if statuses == {"checked"}:
        return "checked"
    if statuses.issubset({"done", "checked"}):
        return "done"
    if statuses & {"in_progress", "done"}:
        return "in_progress"
    return "todo"


async def _ensure_access(user: User, task: Task):
    if user.role == "admin":
        return
    if user.role == "child" and task.child_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    if user.role == "parent":
        # For now, allow parents access to any task; in real app we should check ChildParent link
        return

def make_task_hash(subject_id: int, date, title: str) -> str:
    key = f"{subject_id}:{date}:{title}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()

async def get_task_by_hash(session, child_id: int, hash_value: str):
    return await session.scalar(
        select(Task).where(
            Task.child_id == child_id,
            Task.hash == hash_value
        )
    )

async def get_task_by_subject_date(session, child_id: int, subject_id: int, date):
    return await session.scalar(
       select(Task).where(
            Task.child_id == child_id,
            Task.subject_id == subject_id,
            Task.date == date,
        )
    )

@router.get("/", response_model=List[TaskOut])
async def list_tasks(
    subject_id: Optional[int] = Query(default=None),
    child_id: Optional[int] = Query(default=None),
    start_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end_date: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Task).options(selectinload(Task.subtasks))
    if user.role == "child":
        q = q.where(Task.child_id == user.id)
    elif child_id is not None:
        q = q.where(Task.child_id == child_id)

    if subject_id is not None:
        q = q.where(Task.subject_id == subject_id)

    start_dt = None
    end_dt = None
    if start_date is not None:
        start_dt = _parse_iso_date(start_date, "start_date")
        q = q.where(Task.date >= start_date)
    if end_date is not None:
        end_dt = _parse_iso_date(end_date, "end_date")
        q = q.where(Task.date <= end_date)
    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    result = await db.execute(q.order_by(Task.date.desc(), Task.id.desc()))
    tasks = list(result.scalars().unique().all())
    for t in tasks:
        # compute status from subtasks to ensure consistency
        if t.subtasks:
            t.status = _compute_task_status(t.subtasks)
    return tasks


@router.post("/", response_model=TaskResponse)
async def create_task(
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # --- 1. Child id / defaults  ---
    child_id = payload.child_id
    if user.role == "child":
        child_id = user.id
    elif child_id is None:
        child_id = user.id
    elif user.role != "admin":
        # parents without specified child are not yet supported; fallback to their id
        child_id = user.id

    date_str = payload.date or _today_str()

    # --- 2. Ищем задачу с точно таким subject+date+title ---
    stmt = (
        select(Task)
        .options(selectinload(Task.subtasks))
        .where(
            Task.child_id == child_id,
            Task.subject_id == payload.subject_id,
            Task.date == date_str,
            Task.title == payload.title,
        )
    )
    res = await db.execute(stmt)
    existing_task = res.scalars().unique().first()

    if existing_task:
        # Сравним существующие и входящие подзадачи — добавим только новые
        existing_titles = {s.title for s in existing_task.subtasks}
        incoming_subtasks = payload.subtasks or []
        # сохраним порядок из payload, но добавим только те, которых нет
        new_titles = [s.title for s in incoming_subtasks if s.title not in existing_titles]

        if not new_titles:
            # Полный дубль: ничего не изменилось
            # existing_task уже загружен с selectinload
            return {"status": "duplicate", "task": existing_task}

        # Добавляем новые подзадачи, продолжая позиции
        max_pos = max((s.position or 0) for s in existing_task.subtasks) if existing_task.subtasks else 0
        pos = max_pos
        for title in new_titles:
            pos += 1
            # Найдём объект из payload, чтобы взять type (если есть)
            st_obj = next((s for s in incoming_subtasks if s.title == title), None)
            st_type = getattr(st_obj, "type", None) if st_obj else None
            existing_task.subtasks.append(
                Subtask(
                    title=title,
                    type=st_type,
                    status="todo",
                    position=pos,
                )
            )

        await db.commit()

        # Подгружаем заново с сабтасками, пересчитываем статус и сохраняем
        result = await db.execute(
            select(Task).options(selectinload(Task.subtasks)).where(Task.id == existing_task.id)
        )
        existing_task = result.scalars().unique().one()
        existing_task.status = _compute_task_status(existing_task.subtasks)
        db.add(existing_task)
        await db.commit()
        # refresh not strictly necessary, but безопасно
        await db.refresh(existing_task, attribute_names=["subtasks"])

        return {"status": "updated", "task": existing_task}

    # --- 3. Нет задачи с таким subject+date+title → создаём новую ---
    task_hash = make_task_hash(payload.subject_id, date_str, payload.title)
    task = Task(
        child_id=child_id,
        subject_id=payload.subject_id,
        date=date_str,
        title=payload.title,
        hash=task_hash,
        status="todo",
    )
    db.add(task)

    if payload.subtasks:
        for idx, st in enumerate(payload.subtasks, start=1):
            task.subtasks.append(
                Subtask(
                    title=st.title,
                    type=st.type,
                    status="todo",
                    position=idx,
                )
            )

    # Попытка сохранить; на случай гонки — обработаем IntegrityError по уникальному индексу hash
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Конкурентно создалась аналогичная запись — считаем дубликатом
        dup = await get_task_by_hash(db, child_id, task_hash)
        if dup:
            result = await db.execute(
                select(Task).options(selectinload(Task.subtasks)).where(Task.id == dup.id)
            )
            dup = result.scalars().unique().one()
            return {"status": "duplicate", "task": dup}
        # если тут нет dup — просто пробросим ошибку
        raise

    # Подгружаем задачу вместе с подзадачами
    result = await db.execute(
        select(Task).options(selectinload(Task.subtasks)).where(Task.id == task.id)
    )
    task = result.scalars().unique().one()

    # Пересчёт статуса и сохранение
    if task.subtasks:
        task.status = _compute_task_status(task.subtasks)
        db.add(task)
        await db.commit()
        await db.refresh(task, attribute_names=["subtasks"])

    return {"status": "created", "task": task}


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    task = await db.get(Task, task_id, options=(selectinload(Task.subtasks),))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await _ensure_access(user, task)
    if task.subtasks:
        task.status = _compute_task_status(task.subtasks)
    return task

@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id, options=(selectinload(Task.subtasks),))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await _ensure_access(user, task)
    if payload.title is not None:
        task.title = payload.title
    if payload.status is not None:
        if payload.status not in TASK_STATUS_VALUES:
            raise HTTPException(status_code=400, detail="Invalid status")
        task.status = payload.status
    await db.commit()
    await db.refresh(task)
    if task.subtasks:
        task.status = _compute_task_status(task.subtasks)
    return task


@router.post("/{task_id}/subtasks", response_model=SubtaskOut)
async def create_subtask(
    task_id: int,
    payload: SubtaskCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await db.get(Task, task_id, options=(selectinload(Task.subtasks),))
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    await _ensure_access(user, task)
    position = (max((s.position or 0) for s in task.subtasks) + 1) if task.subtasks else 1
    st = Subtask(task_id=task.id, title=payload.title, status="todo", position=position)
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@router.patch("/subtasks/{subtask_id}", response_model=SubtaskOut)
async def update_subtask(
    subtask_id: int,
    payload: SubtaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    st = await db.get(Subtask, subtask_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtask not found")
    task = await db.get(Task, st.task_id, options=(selectinload(Task.subtasks),))
    await _ensure_access(user, task)
    if payload.title is not None:
        st.title = payload.title
    if payload.status is not None:
        if payload.status not in TASK_STATUS_VALUES:
            raise HTTPException(status_code=400, detail="Invalid status")
        st.status = payload.status
    if payload.parent_reaction is not None:
        st.parent_reaction = payload.parent_reaction
    await db.commit()
    await db.refresh(st)
    # also refresh task status
    task.status = _compute_task_status(task.subtasks)
    await db.commit()
    return st


@router.post("/subtasks/{subtask_id}/start", response_model=SubtaskOut)
async def start_subtask(subtask_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    st = await db.get(Subtask, subtask_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtask not found")
    task = await db.get(Task, st.task_id, options=(selectinload(Task.subtasks),))
    await _ensure_access(user, task)
    if st.status == "todo":
        st.status = "in_progress"
        await db.commit()
    await db.refresh(st)
    # Update task status
    task.status = _compute_task_status(task.subtasks)
    await db.commit()
    return st


@router.post("/subtasks/{subtask_id}/complete", response_model=SubtaskOut)
async def complete_subtask(subtask_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    st = await db.get(Subtask, subtask_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtask not found")
    task = await db.get(Task, st.task_id, options=(selectinload(Task.subtasks),))
    await _ensure_access(user, task)
    st.status = "done"
    await db.commit()
    await db.refresh(st)
    task.status = _compute_task_status(task.subtasks)
    await db.commit()
    return st


@router.delete("/{task_id}", response_model=StatusResponse)
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    task = await db.get(Task, task_id, options=(selectinload(Task.subtasks),))
    if not task:
        return StatusResponse(status="not_found")
    await _ensure_access(user, task)
    await db.delete(task)
    await db.commit()
    return StatusResponse(status="deleted")


@router.post("/subtasks/{subtask_id}/check", response_model=SubtaskOut)
async def check_subtask(subtask_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    st = await db.get(Subtask, subtask_id)
    if not st:
        raise HTTPException(status_code=404, detail="Subtask not found")
    task = await db.get(Task, st.task_id, options=(selectinload(Task.subtasks),))
    await _ensure_access(user, task)
    st.status = "checked"
    await db.commit()
    await db.refresh(st)
    task.status = _compute_task_status(task.subtasks)
    await db.commit()
    return st


@router.delete("/subtasks/{subtask_id}", response_model=StatusResponse)
async def delete_subtask(subtask_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    st = await db.get(Subtask, subtask_id)
    if not st:
        return StatusResponse(status="not_found")
    task = await db.get(Task, st.task_id, options=(selectinload(Task.subtasks),))
    await _ensure_access(user, task)
    await db.delete(st)
    await db.commit()
    return StatusResponse(status="deleted")
