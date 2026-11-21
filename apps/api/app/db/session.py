from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


def to_sync_database_url(database_url: str) -> str:
    """Convert supported async database URLs to their synchronous drivers."""
    url = make_url(database_url)
    if url.drivername == "sqlite+aiosqlite":
        url = url.set(drivername="sqlite")
    return url.render_as_string(hide_password=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Create and cache the asynchronous SQLAlchemy engine using Psycopg 3 or aiosqlite."""
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("PFA_DATABASE_URL is not configured.")

    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Provide a cached async sessionmaker."""
    return async_sessionmaker(
        bind=get_async_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


@lru_cache(maxsize=1)
def get_sync_engine() -> Any:
    """Provide a synchronous engine (used for Alembic migrations or scripts)."""
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("PFA_DATABASE_URL is not configured.")

    return create_engine(
        to_sync_database_url(settings.database_url),
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_sync_session_factory() -> sessionmaker[Session]:
    """Provide a cached synchronous sessionmaker."""
    return sessionmaker(
        bind=get_sync_engine(),
        autoflush=False,
        autocommit=False,
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session and closing it on exit."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
