import os
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import src.evaluation.queue as _eval_queue_compat  # noqa: F401
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


def get_safe_test_database_url() -> str:
    """Obtiene y valida la URL de conexión exclusiva para pruebas.
    
    Reglas de protección estricta (S3.1):
    - Si existe la variable TEST_DATABASE_URL, se utiliza esa URL.
    - Si no existe, se deriva reemplazando el nombre de la base de datos por 'evaluador_test_db'.
    - NUNCA se permite ejecutar pruebas sobre 'evaluador_db' ni bases productivas/desarrollo.
    """
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        base_url = settings.DATABASE_URL
        if "/evaluador_db" in base_url:
            raw_url = base_url.replace("/evaluador_db", "/evaluador_test_db")
        else:
            raw_url = base_url

    validate_test_database_url(raw_url)
    return raw_url


def validate_test_database_url(url: str) -> None:
    """Valida que la URL apunte a una base de datos de pruebas segura y aislada."""
    # Extraer nombre de la base de datos de la URL
    clean_url = url.split("?")[0].rstrip("/")
    db_name = clean_url.split("/")[-1] if "/" in clean_url else ""

    forbidden_names = {"evaluador_db", "production", "prod", "evaluador_prod_db", "evaluador_dev"}
    if db_name in forbidden_names or not db_name.endswith(("_test", "_test_db")):
        raise RuntimeError(
            f"REFUSED: Safety check failed. Tests cannot run against development or production database '{db_name}'. "
            f"Tests MUST use a dedicated test database such as 'evaluador_test_db'. Configure TEST_DATABASE_URL."
        )


@pytest.fixture
def database_url() -> str:
    return get_safe_test_database_url()


@pytest.fixture(autouse=True)
async def isolate_database_and_engine(database_url: str) -> AsyncGenerator[None, None]:
    validate_test_database_url(database_url)

    original_db_url = settings.DATABASE_URL
    settings.DATABASE_URL = database_url

    import src.db.session as db_session_module

    if db_session_module._engine is not None:
        await db_session_module._engine.dispose()
    db_session_module._engine = None
    db_session_module._async_session_maker = None
    db_session_module._sync_engine = None
    db_session_module._sync_session_maker = None

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database()"))
            current_database = result.scalar_one()

            if current_database == "evaluador_db" or not current_database.endswith(("_test", "_test_db")):
                raise RuntimeError(
                    f"FATAL: Connected to database '{current_database}' which is not a dedicated test database! "
                    "Aborting execution immediately to prevent data destruction."
                )

            await connection.execute(text("DROP TABLE IF EXISTS s4_task_executions, s4_load_runs CASCADE;"))
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text(
                    "TRUNCATE TABLE organizations, users, memberships, vacancies, problems, "
                    "interviews, turns, snapshots, invitations, evaluations, "
                    "evaluation_dimensions, evaluation_evidence, llm_usage_records, "
                    "s4_task_executions, s4_load_runs RESTART IDENTITY CASCADE;"
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
    db_session_module._sync_engine = None
    db_session_module._sync_session_maker = None
    settings.DATABASE_URL = original_db_url


@pytest.fixture
async def db_session(database_url: str) -> AsyncGenerator[AsyncSession, None]:
    validate_test_database_url(database_url)
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database()"))
            current_database = result.scalar_one()
            if current_database != "evaluador_test_db" and not current_database.endswith(("_test", "_test_db")):
                pytest.skip(
                    f"NO EJECUTADO — PostgreSQL no es evaluador_test_db (recibido: {current_database})"
                )
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            yield session
            await session.rollback()
    except (OSError, OperationalError) as exc:
        pytest.skip(f"NO EJECUTADO — PostgreSQL test db no disponible: {exc}")
    finally:
        await engine.dispose()


