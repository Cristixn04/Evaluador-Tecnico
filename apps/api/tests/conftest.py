from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.db.base import Base
from src.db.models import Interview, Problem, Snapshot, Turn, Vacancy

_ = (Interview, Problem, Snapshot, Turn, Vacancy)


@pytest.fixture
def database_url() -> str:
    return settings.DATABASE_URL


@pytest.fixture
async def db_session(database_url: str) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database()"))
            current_database = result.scalar_one()
            if current_database != "evaluador_db":
                pytest.skip(
                    f"NO EJECUTADO — PostgreSQL no es evaluador_db (recibido: {current_database})"
                )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            yield session
            await session.rollback()
    except (OSError, OperationalError) as exc:
        pytest.skip(f"NO EJECUTADO — PostgreSQL no disponible: {exc}")
    finally:
        await engine.dispose()
