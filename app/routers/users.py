from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..db import get_db
from ..models import User, ChildParent
from ..schemas import UserOut, UserUpdate, LinkRequest, StatusResponse
from ..auth import get_current_user, require_roles, get_password_hash


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/link", response_model=StatusResponse)
async def link_parent_child(
    payload: LinkRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only admin or a parent linking themselves to a child
    if user.role not in {"admin", "parent"}:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if user.role == "parent" and payload.parent_id != user.id:
        raise HTTPException(status_code=403, detail="Parents can only link themselves")

    parent = await db.get(User, payload.parent_id)
    child = await db.get(User, payload.child_id)
    if not parent or not child:
        raise HTTPException(status_code=404, detail="Parent or child not found")
    if parent.role != "parent" or child.role != "child":
        raise HTTPException(status_code=400, detail="Roles mismatch for link")

    # Check existing
    exists = await db.execute(
        select(ChildParent).where(
            (ChildParent.parent_id == payload.parent_id) & (ChildParent.child_id == payload.child_id)
        )
    )
    if exists.scalar_one_or_none():
        return StatusResponse(status="linked")

    link = ChildParent(parent_id=payload.parent_id, child_id=payload.child_id, relation_type=payload.relation_type)
    db.add(link)
    await db.commit()
    return StatusResponse(status="linked")


# Admin-only CRUD


@router.get("/", response_model=List[UserOut], dependencies=[Depends(require_roles("admin"))])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles("admin"))])
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles("admin"))])
async def update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.name is not None:
        user.name = payload.name
    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        if payload.role not in {"child", "parent", "admin"}:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = payload.role
    if payload.password is not None:
        user.password_hash = get_password_hash(payload.password)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=StatusResponse, dependencies=[Depends(require_roles("admin"))])
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return StatusResponse(status="deleted")

