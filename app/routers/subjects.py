from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user, require_roles
from ..db import get_db
from ..models import User, Subject, ChildSubject
from ..schemas import SubjectCreate, SubjectOut


router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("/", response_model=List[SubjectOut])
async def list_subjects(
    child_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role == "child":
        # subjects linked to the child
        subq = select(ChildSubject.subject_id).where(ChildSubject.child_id == user.id).subquery()
        result = await db.execute(select(Subject).where(Subject.id.in_(select(subq.c.subject_id))))
        return list(result.scalars().all())
    # parent/admin: if child_id provided, filter by it; otherwise, list all
    if child_id is not None:
        subq = select(ChildSubject.subject_id).where(ChildSubject.child_id == child_id).subquery()
        result = await db.execute(select(Subject).where(Subject.id.in_(select(subq.c.subject_id))))
        return list(result.scalars().all())
    result = await db.execute(select(Subject).order_by(Subject.name.asc()))
    return list(result.scalars().all())


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

