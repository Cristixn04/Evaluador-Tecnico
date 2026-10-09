import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]


def test_initial_migration_is_registered() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())
    assert [item.revision for item in revisions] == ["0002_auth_s03", "0001_initial_s02"]
    assert revisions[0].down_revision == "0001_initial_s02"
    assert revisions[1].down_revision is None


async def _public_tables(engine) -> set[str]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' AND tablename != 'alembic_version'"
            )
        )
        return set(result.scalars().all())


async def _reset_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.asyncio
async def test_alembic_upgrade_and_downgrade() -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            current_database = (
                await connection.execute(text("SELECT current_database()"))
            ).scalar_one()
            if current_database != "evaluador_db":
                pytest.skip(
                    f"NO EJECUTADO — PostgreSQL no es evaluador_db (recibido: {current_database})"
                )
        await _reset_schema(engine)
    except (OSError, OperationalError) as exc:
        pytest.skip(f"NO EJECUTADO — PostgreSQL no disponible: {exc}")
    finally:
        await engine.dispose()

    upgrade = _run_alembic("upgrade", "head")
    if upgrade.returncode != 0:
        pytest.fail(f"alembic upgrade head falló:\n{upgrade.stdout}\n{upgrade.stderr}")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        tables = await _public_tables(engine)
        assert tables == {
            "organizations",
            "users",
            "memberships",
            "vacancies",
            "problems",
            "interviews",
            "turns",
            "snapshots",
        }
        async with engine.connect() as connection:
            version = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            assert version == "0002_auth_s03"
    finally:
        await engine.dispose()

    downgrade = _run_alembic("downgrade", "base")
    if downgrade.returncode != 0:
        pytest.fail(f"alembic downgrade base falló:\n{downgrade.stdout}\n{downgrade.stderr}")

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        tables = await _public_tables(engine)
        assert tables == set()
    finally:
        await engine.dispose()

    reupgrade = _run_alembic("upgrade", "head")
    if reupgrade.returncode != 0:
        pytest.fail(
            f"alembic upgrade head (reapply) falló:\n{reupgrade.stdout}\n{reupgrade.stderr}"
        )
