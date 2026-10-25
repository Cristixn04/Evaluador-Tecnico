from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings
from src.db.base import Base
from src.db.models import (
    Interview,
    Membership,
    Organization,
    Problem,
    Snapshot,
    Turn,
    User,
    Vacancy,
)

_ = (Interview, Membership, Organization, Problem, Snapshot, Turn, User, Vacancy)


@pytest.fixture
def database_url() -> str:
    return settings.DATABASE_URL


@pytest.fixture(autouse=True)
async def isolate_database_and_engine(database_url: str) -> AsyncGenerator[None, None]:
    import src.db.session as db_session_module

    if db_session_module._engine is not None:
        await db_session_module._engine.dispose()
    db_session_module._engine = None
    db_session_module._async_session_maker = None

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database()"))
            current_database = result.scalar_one()
            if current_database in ("evaluador_db", "evaluador_test_db"):
                await connection.run_sync(Base.metadata.create_all)
                await connection.execute(
                    text(
                        "TRUNCATE TABLE organizations, users, memberships, vacancies, problems, "
                        "interviews, turns, snapshots, invitations, evaluations, "
                        "evaluation_dimensions, evaluation_evidence RESTART IDENTITY CASCADE;"
                    )
                )
                await connection.commit()
    except (OSError, OperationalError):
        pass
    finally:
        await engine.dispose()

    yield

    if db_session_module._engine is not None:
        await db_session_module._engine.dispose()
    db_session_module._engine = None
    db_session_module._async_session_maker = None


@pytest.fixture
async def db_session(database_url: str) -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database()"))
            current_database = result.scalar_one()
            if current_database not in ("evaluador_db", "evaluador_test_db"):
                pytest.skip(
                    f"NO EJECUTADO — PostgreSQL no es evaluador_db o evaluador_test_db (recibido: {current_database})"
                )
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            yield session
            await session.rollback()
    except (OSError, OperationalError) as exc:
        pytest.skip(f"NO EJECUTADO — PostgreSQL no disponible: {exc}")
    finally:
        await engine.dispose()

