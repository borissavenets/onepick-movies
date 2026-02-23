"""Database engine and session configuration."""

import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def _get_database_url() -> str:
    """Get database URL from environment or config."""
    # Try environment first (for Alembic/migrations)
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    # Fall back to config (lazy import to avoid circular deps)
    try:
        from app.config import config
        return config.database_url
    except Exception:
        return "sqlite+aiosqlite:///./onepick.db"


def _get_log_level() -> str:
    """Get log level from environment or config."""
    level = os.getenv("LOG_LEVEL")
    if level:
        return level.upper()

    try:
        from app.config import config
        return config.log_level
    except Exception:
        return "INFO"


def get_engine() -> AsyncEngine:
    """Get or create the database engine.

    Returns:
        AsyncEngine instance configured for the application
    """
    global _engine

    if _engine is None:
        from app.logging import get_logger
        logger = get_logger(__name__)

        database_url = _get_database_url()
        log_level = _get_log_level()

        logger.info(f"Creating database engine for {database_url}")
        _engine = create_async_engine(
            database_url,
            echo=log_level == "DEBUG",
            pool_pre_ping=True,
        )

    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory.

    Returns:
        Session factory for creating database sessions
    """
    global _session_factory

    if _session_factory is None:
        engine = get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    return _session_factory


async def close_engine() -> None:
    """Close the database engine and dispose connections."""
    global _engine, _session_factory

    if _engine is not None:
        from app.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Closing database engine")
        await _engine.dispose()
        _engine = None
        _session_factory = None
