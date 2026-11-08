"""Tests for deployment pipeline, container entrypoint, and infrastructure configuration (S-25)."""

import os
import subprocess
import tomllib
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INFRA_DIR = REPO_ROOT / "infra"


def test_entrypoint_script_exists_and_executable():
    """Verify infra/entrypoint.sh exists and has execute permissions."""
    entrypoint_path = INFRA_DIR / "entrypoint.sh"
    assert entrypoint_path.exists(), "infra/entrypoint.sh must exist"
    assert os.access(entrypoint_path, os.X_OK), "infra/entrypoint.sh must be executable"


def test_entrypoint_content_structure():
    """Verify entrypoint contains readiness check, alembic upgrade, and exec."""
    entrypoint_path = INFRA_DIR / "entrypoint.sh"
    content = entrypoint_path.read_text(encoding="utf-8")

    assert "alembic upgrade head" in content, "Entrypoint must invoke alembic upgrade head"
    assert 'exec "$@"' in content, "Entrypoint must exec the original command"
    assert "DATABASE_URL" in content, "Entrypoint must handle DATABASE_URL readiness check"
    assert "AUTO_MIGRATE" in content, "Entrypoint should support AUTO_MIGRATE toggle"

    # Ensure migration precedes exec
    migration_idx = content.index("alembic upgrade head")
    exec_idx = content.index('exec "$@"')
    assert migration_idx < exec_idx, "Alembic migrations must precede uvicorn/app execution"


def test_entrypoint_behavior_auto_migrate_disabled(tmp_path):
    """Test running entrypoint with AUTO_MIGRATE=0 skips alembic and executes command."""
    entrypoint_path = INFRA_DIR / "entrypoint.sh"
    # Execute a simple echo command through entrypoint with AUTO_MIGRATE=0 and no DATABASE_URL
    env = os.environ.copy()
    env["AUTO_MIGRATE"] = "0"
    env["DATABASE_URL"] = ""

    result = subprocess.run(
        [str(entrypoint_path), "echo", "SERVER_STARTED"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "AUTO_MIGRATE=0: Omitiendo ejecución de migraciones" in result.stdout
    assert "SERVER_STARTED" in result.stdout


def test_entrypoint_fails_when_migrations_fail(tmp_path):
    """Test that entrypoint aborts and returns non-zero when alembic command fails."""
    # Create a mock alembic script in a temporary PATH that fails
    mock_bin_dir = tmp_path / "bin"
    mock_bin_dir.mkdir()
    mock_alembic = mock_bin_dir / "alembic"
    mock_alembic.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    mock_alembic.chmod(0o755)

    entrypoint_path = INFRA_DIR / "entrypoint.sh"
    env = os.environ.copy()
    env["PATH"] = f"{mock_bin_dir}:{env.get('PATH', '')}"
    env["AUTO_MIGRATE"] = "1"
    env["DATABASE_URL"] = ""

    result = subprocess.run(
        [str(entrypoint_path), "echo", "SHOULD_NOT_EXECUTE"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert "SHOULD_NOT_EXECUTE" not in result.stdout
    assert "La migración de base de datos falló" in result.stderr


def test_dockerfile_configuration():
    """Verify Dockerfile.api includes entrypoint, correct alembic path, and healthcheck."""
    dockerfile_path = INFRA_DIR / "Dockerfile.api"
    assert dockerfile_path.exists(), "infra/Dockerfile.api must exist"
    content = dockerfile_path.read_text(encoding="utf-8")

    # Correct alembic directory path
    assert "COPY apps/api/alembic ./alembic" in content
    assert "COPY apps/api/migrations" not in content, "Old migrations path should not be referenced"

    # Entrypoint setup
    assert "COPY infra/entrypoint.sh /app/entrypoint.sh" in content
    assert 'ENTRYPOINT ["/app/entrypoint.sh"]' in content
    assert "USER appuser" in content

    # Healthcheck
    assert "HEALTHCHECK" in content
    assert "/health" in content


def test_fly_toml_configuration():
    """Verify infra/fly.toml is valid TOML and specifies release_command and checks."""
    fly_path = INFRA_DIR / "fly.toml"
    assert fly_path.exists(), "infra/fly.toml must exist"

    with open(fly_path, "rb") as f:
        data = tomllib.load(f)

    assert data.get("app") == "evaluador-tecnico-api"
    assert data.get("build", {}).get("dockerfile") == "infra/Dockerfile.api"
    assert data.get("deploy", {}).get("release_command") == "alembic upgrade head"
    assert data.get("env", {}).get("AUTO_MIGRATE") == "0"

    http_service = data.get("http_service", {})
    assert http_service.get("internal_port") == 8000
    checks = http_service.get("checks", [])
    assert len(checks) >= 1
    assert checks[0].get("path") == "/health"


def test_docker_compose_prod_configuration():
    """Verify docker-compose.prod.yml includes required services and dependency conditions."""
    compose_path = INFRA_DIR / "docker-compose.prod.yml"
    assert compose_path.exists(), "infra/docker-compose.prod.yml must exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    services = data.get("services", {})
    assert "api" in services
    assert "postgres" in services
    assert "redis" in services

    api_service = services["api"]
    depends_on = api_service.get("depends_on", {})
    assert "postgres" in depends_on
    assert depends_on["postgres"].get("condition") == "service_healthy"

    postgres_service = services["postgres"]
    assert "healthcheck" in postgres_service
