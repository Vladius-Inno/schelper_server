import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from ..db import get_db
from ..models import User, RefreshToken
from ..schemas import UserCreate, RegisterResponse, LoginRequest, TokenResponse, RefreshRequest
from ..auth import get_password_hash, verify_password, create_access_token, ALLOWED_ROLES
from ..config import settings


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegisterResponse)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.flush()  # assign id
    token = create_access_token(user_id=user.id, role=user.role)
    await db.commit()
    return RegisterResponse(id=user.id, name=user.name, email=user.email, role=user.role, token=token)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(user_id=user.id, role=user.role)

    # Create a refresh token: opaque random string stored hashed in DB
    raw_refresh = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expires_days)
    rt = RefreshToken(
        user_id=user.id,
        token_hash=get_password_hash(raw_refresh),
        expires_at=expires_at,
    )
    db.add(rt)
    await db.commit()
    return TokenResponse(token=access_token, refresh_token=raw_refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    # naive search: pull all candidate tokens for later verification. For perf, we could store plain hash and query by it.
    result = await db.execute(select(RefreshToken).where(RefreshToken.revoked == False))  # noqa: E712
    tokens = result.scalars().all()

    # Find a matching token by verifying hash
    match: RefreshToken | None = None
    for t in tokens:
        if verify_password(payload.refresh_token, t.token_hash):
            match = t
            break
    if match is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if match.expires_at < datetime.now(timezone.utc) or match.revoked:
        raise HTTPException(status_code=401, detail="Expired or revoked refresh token")

    # Issue a new access token
    user = (await db.get(User, match.user_id))
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    token = create_access_token(user_id=user.id, role=user.role)
    return TokenResponse(token=token)

