from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings

_engine = None
_async_session_maker = None
_sync_engine = None
_sync_session_maker = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return _engine


def get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        # Convert async URL to sync URL (replace asyncpg with psycopg2)
        sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        _sync_engine = create_engine(sync_url, pool_pre_ping=True)
    return _sync_engine


def get_session_maker():
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session_maker


def get_sync_session_maker():
    global _sync_session_maker
    if _sync_session_maker is None:
        _sync_session_maker = sessionmaker(get_sync_engine(), class_=Session, expire_on_commit=False)
    return _sync_session_maker


# Backwards compatibility: provide engine and async_session_maker as lazily-initialized objects
class _LazyEngine:
    def __getattr__(self, name):
        return getattr(get_engine(), name)

    def __call__(self, *args, **kwargs):
        return get_engine()(*args, **kwargs)


class _LazySessionMaker:
    def __getattr__(self, name):
        return getattr(get_session_maker(), name)

    def __call__(self, *args, **kwargs):
        return get_session_maker()(*args, **kwargs)


engine = _LazyEngine()
async_session_maker = _LazySessionMaker()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_maker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db() -> Generator[Session, None, None]:
    with get_sync_session_maker()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
