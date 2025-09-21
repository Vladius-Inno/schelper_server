from typing import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from .config import settings


class Base(DeclarativeBase):
    pass


def _normalize_database_url(url: str) -> str:
    # Ensure async driver for Postgres
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        # driver not specified
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    elif url.startswith("postgresql+psycopg2://"):
        url = "postgresql+asyncpg://" + url[len("postgresql+psycopg2://") :]
    return url


logger = logging.getLogger("uvicorn.error")


def _redact_url(url: str) -> str:
    try:
        # Mask password if present: scheme://user:pass@host -> scheme://user:***@host
        if "@" in url and "://" in url:
            scheme_sep = url.split("://", 1)
            scheme, rest = scheme_sep[0], scheme_sep[1]
            if "@" in rest and ":" in rest.split("@", 1)[0]:
                creds, host = rest.split("@", 1)
                user, _pwd = creds.split(":", 1)
                return f"{scheme}://{user}:***@{host}"
    except Exception:
        pass
    return url


DB_URL = _normalize_database_url(settings.database_url)
engine = create_async_engine(DB_URL, echo=False, future=True, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    # Ensure we can connect and create tables
    try:
        logger.info("DB init starting. URL=%s", _redact_url(DB_URL))
        async with engine.begin() as conn:
            # Set pragmas for sqlite for FK if needed
            if DB_URL.startswith("sqlite"):
                await conn.execute(text("PRAGMA foreign_keys=ON"))
            from . import models  # noqa: F401 - ensure models are imported for metadata
            await conn.run_sync(Base.metadata.create_all)
            # Verify a few expected tables exist
            from sqlalchemy import inspect as sa_inspect

            def _inspect(sync_conn):
                insp = sa_inspect(sync_conn)
                return {
                    name: insp.has_table(name)
                    for name in [
                        "users",
                        "children_parents",
                        "children_subjects",
                        "subjects",
                        "refresh_tokens",
                    ]
                }

            exists = await conn.run_sync(_inspect)
            logger.info("DB init complete. Tables: %s", exists)
    except Exception as e:
        logger.exception("Database initialization failed: %s", e)
        raise


async def inspect_db_state() -> dict:
    """Return current DB URL (redacted) and table existence flags."""
    async with engine.begin() as conn:
        from sqlalchemy import inspect as sa_inspect

        def _inspect(sync_conn):
            insp = sa_inspect(sync_conn)
            return {
                name: insp.has_table(name)
                for name in [
                    "users",
                    "children_parents",
                    "children_subjects",
                    "subjects",
                    "refresh_tokens",
                ]
            }

        tables = await conn.run_sync(_inspect)
        return {"database_url": _redact_url(DB_URL), "tables": tables}
