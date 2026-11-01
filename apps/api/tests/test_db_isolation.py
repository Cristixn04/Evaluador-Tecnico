"""Pruebas unitarias de aislamiento de base de datos y protección contra truncado accidental (S3.1)."""

import pytest

from tests.conftest import get_safe_test_database_url, validate_test_database_url


def test_validate_test_database_url_accepts_test_db() -> None:
    # URLs seguras de pruebas
    safe_urls = [
        "postgresql+asyncpg://evaluador:secret@localhost:5435/evaluador_test_db",
        "postgresql+asyncpg://user:pass@127.0.0.1:5432/my_app_test",
        "postgresql+asyncpg://user:pass@localhost/ci_runner_test_db?ssl=disable",
    ]
    for url in safe_urls:
        # No debe lanzar excepción
        validate_test_database_url(url)


def test_validate_test_database_url_rejects_evaluador_db() -> None:
    unsafe_url = "postgresql+asyncpg://evaluador:evaluador_password_dev@localhost:5435/evaluador_db"
    with pytest.raises(RuntimeError, match="REFUSED: Safety check failed"):
        validate_test_database_url(unsafe_url)


def test_validate_test_database_url_rejects_production_names() -> None:
    unsafe_urls = [
        "postgresql+asyncpg://admin:secret@prod.server:5432/production",
        "postgresql+asyncpg://admin:secret@prod.server:5432/evaluador_prod_db",
        "postgresql+asyncpg://admin:secret@prod.server:5432/evaluador_dev",
        "postgresql+asyncpg://admin:secret@prod.server:5432/evaluador",
    ]
    for url in unsafe_urls:
        with pytest.raises(RuntimeError, match="REFUSED: Safety check failed"):
            validate_test_database_url(url)


def test_get_safe_test_database_url_derives_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    url = get_safe_test_database_url()
    assert "evaluador_test_db" in url
    assert "evaluador_db" not in url.split("/")[-1]
