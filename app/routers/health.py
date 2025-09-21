from fastapi import APIRouter

from ..db import inspect_db_state


router = APIRouter(prefix="/healthz", tags=["health"])


@router.get("/")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/db")
async def health_db() -> dict:
    return await inspect_db_state()

