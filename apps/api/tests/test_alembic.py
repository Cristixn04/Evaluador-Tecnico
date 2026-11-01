import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.conftest import get_safe_test_database_url

API_ROOT = Path(__file__).resolve().parents[1]


async def test_initial_migration_is_registered() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    revisions = list(script.walk_revisions())
    assert [item.revision for item in revisions] == [
        "s3_add_llm_usage_records",
        "merge_evaluation_invitations",
        "9e72f0a31071",
        "adding_evaluation_tables",
        "a5fe8eec0469",
        "b217eca9217b",
        "adding_trajectory_fields",
        "9d55e0bb5769",
        "02c74c24508e",
        "8d9dc162d3fd",
        "0005_access_token_null",
        "0004_add_token_selector",
        "0003_s09_invitation_phase",
        "0002_auth_s03",
        "0001_initial_s02",
    ]
    assert script.get_heads() == ["s3_add_llm_usage_records"]


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


def _run_alembic(*args: str, db_url: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if db_url:
        env["ALEMBIC_DATABASE_URL"] = db_url
        env["TEST_DATABASE_URL"] = db_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.mark.asyncio
async def test_alembic_upgrade_and_downgrade() -> None:
    test_db_url = get_safe_test_database_url()
    engine = create_async_engine(test_db_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            current_database = (
                await connection.execute(text("SELECT current_database()"))
            ).scalar_one()
            if current_database == "evaluador_db" or not current_database.endswith(("_test", "_test_db")):
                pytest.fail(
                    f"SEGURIDAD: test_alembic_upgrade_and_downgrade debe ejecutarse únicamente sobre la base de pruebas aislada (detectada: {current_database})"
                )
        await _reset_schema(engine)
    except (OSError, OperationalError) as exc:
        pytest.skip(f"NO EJECUTADO — PostgreSQL no disponible: {exc}")
    finally:
        await engine.dispose()

    upgrade = _run_alembic("upgrade", "head", db_url=test_db_url)
    if upgrade.returncode != 0:
        pytest.fail(f"alembic upgrade head falló:\n{upgrade.stdout}\n{upgrade.stderr}")

    engine = create_async_engine(test_db_url, pool_pre_ping=True)
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
            "invitations",
            "evaluations",
            "evaluation_dimensions",
            "evaluation_evidence",
            "llm_usage_records",
        }
        async with engine.connect() as connection:
            version = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            assert version == "s3_add_llm_usage_records"
    finally:
        await engine.dispose()

    downgrade = _run_alembic("downgrade", "base", db_url=test_db_url)
    if downgrade.returncode != 0:
        pytest.fail(f"alembic downgrade base falló:\n{downgrade.stdout}\n{downgrade.stderr}")

    engine = create_async_engine(test_db_url, pool_pre_ping=True)
    try:
        tables = await _public_tables(engine)
        assert tables == set()
    finally:
        await engine.dispose()

    reupgrade = _run_alembic("upgrade", "head", db_url=test_db_url)
    if reupgrade.returncode != 0:
        pytest.fail(
            f"alembic upgrade head (reapply) falló:\n{reupgrade.stdout}\n{reupgrade.stderr}"
        )