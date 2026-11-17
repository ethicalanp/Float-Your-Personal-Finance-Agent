from collections.abc import AsyncGenerator
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


@lru_cache(maxsize=1)
def get_async_engine() -> AsyncEngine:
    """Create and cache the asynchronous SQLAlchemy engine."""
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("PFA_DATABASE_URL is not configured.")

    url = settings.database_url
    if not (url.startswith("postgresql+asyncpg://") or url.startswith("sqlite+aiosqlite://")):
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql+pg8000://"):
            url = url.replace("postgresql+pg8000://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql+psycopg://"):
            url = url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)

    return create_async_engine(
        url,
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
    """Provide a synchronous engine (used for migrations or synchronous scripts)."""
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError("PFA_DATABASE_URL is not configured.")

    url = settings.database_url
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+pg8000://", 1)

    return create_engine(
        url,
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
    """Provide an asynchronous database session and close it afterward."""
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
