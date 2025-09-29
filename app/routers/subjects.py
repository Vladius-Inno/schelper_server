from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_roles
from ..db import get_db
from ..models import User, Subject, ChildSubject, Task
from ..schemas import SubjectCreate, SubjectOut, SubjectUpdate


router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/", response_model=List[SubjectOut])
async def list_subjects(
    child_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    async def _subjects_for_child(target_child_id: int):
        subject_ids = set()
        result = await db.execute(select(ChildSubject.subject_id).where(ChildSubject.child_id == target_child_id))
        subject_ids.update(result.scalars().all())
        result = await db.execute(select(Task.subject_id).where(Task.child_id == target_child_id))
        subject_ids.update(result.scalars().all())
        if not subject_ids:
            return []
        result = await db.execute(
            select(Subject)
            .where(Subject.id.in_(subject_ids))
            .order_by(Subject.name.asc())
        )
        return list(result.scalars().unique().all())

    if user.role == "child":
        return await _subjects_for_child(user.id)
    if child_id is not None:
        return await _subjects_for_child(child_id)
    result = await db.execute(select(Subject).order_by(Subject.name.asc()))
    return list(result.scalars().unique().all())

@router.post("/", response_model=SubjectOut, dependencies=[Depends(require_roles("admin"))])
async def create_subject(payload: SubjectCreate, db: AsyncSession = Depends(get_db)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    # unique by name enforced at DB level
    subject = Subject(name=name)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


@router.put("/{subject_id}", response_model=SubjectOut, dependencies=[Depends(require_roles("admin"))])
async def update_subject(subject_id: int, payload: SubjectUpdate, db: AsyncSession = Depends(get_db)):
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    subject.name = name
    await db.commit()
    await db.refresh(subject)
    return subject


@router.delete("/{subject_id}", response_model=SubjectOut, dependencies=[Depends(require_roles("admin"))])
async def delete_subject(subject_id: int, db: AsyncSession = Depends(get_db)):
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    response = SubjectOut.model_validate(subject)
    await db.delete(subject)
    await db.commit()
    return response


async def get_subject_id_by_name(name: str, db: AsyncSession) -> int:
    """Возвращает ID предмета по его названию."""
    normalized_name = name.strip().lower()

    result = await db.execute(
        select(Subject).where(Subject.name.ilike(normalized_name))
    )
    subject = result.scalar_one_or_none()

    if not subject:
        raise HTTPException(status_code=404, detail=f"Subject '{name}' not found")

    return subject.id