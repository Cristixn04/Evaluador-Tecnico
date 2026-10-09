from pathlib import Path

import pytest
from pydantic import ValidationError

from src.problems.exceptions import (
    ProblemCatalogEmptyError,
    ProblemCatalogInvalidError,
    ProblemCatalogNotFoundError,
)
from src.problems.loader import DEFAULT_CATALOG_DIR, ProblemLoader
from src.problems.schemas import ProblemSpec

EXPECTED_IDS = [
    "cache-invalidation",
    "circuit-breaker",
    "configurable-payroll",
    "csv-bulk-processing",
    "feature-flags",
    "geospatial-search",
    "idempotent-webhook",
    "microservice-log-analysis",
    "priority-queue-scheduler",
    "pse-payment-reconciliation",
    "sliding-window-rate-limiter",
    "sql-schema-migration",
]


def _write_yaml(directory: Path, name: str, body: str) -> Path:
    path = directory / f"{name}.yaml"
    path.write_text(body, encoding="utf-8")
    return path


VALID_YAML = """
id: sample-problem
title: Sample
role: backend
seniority: junior
difficulty: junior
tags: [python]
languages: [python]
statement: |
  Do something.
tests:
  - id: case-one
    input: "{}"
    expected_output: "{}"
boilerplate:
  python: "print(1)"
"""


def test_default_catalog_loads_twelve_valid_problems() -> None:
    specs = ProblemLoader(DEFAULT_CATALOG_DIR).load()
    assert [spec.id for spec in specs] == EXPECTED_IDS
    assert len(specs) == 12
    for spec in specs:
        assert spec.tests
        assert spec.tags
        assert spec.languages
        assert spec.statement
        assert spec.persistence_id().version == 5


def test_catalog_load_is_deterministic() -> None:
    loader = ProblemLoader(DEFAULT_CATALOG_DIR)
    first = loader.load()
    second = loader.load()
    assert first is second
    reloaded = loader.reload()
    assert [item.id for item in reloaded] == [item.id for item in first]


def test_concrete_problems_have_expected_metadata() -> None:
    loader = ProblemLoader(DEFAULT_CATALOG_DIR)
    pse = loader.get("pse-payment-reconciliation")
    assert pse.role.value == "backend"
    assert pse.seniority.value == "mid"
    assert "payments" in pse.tags
    assert pse.primary_language == "python"

    payroll = loader.get("configurable-payroll")
    assert payroll.difficulty.value == "mid"
    assert len(payroll.tests) == 3

    flags = loader.get("feature-flags")
    assert flags.languages[0].value == "javascript"
    assert "javascript" in flags.boilerplate


def test_schema_rejects_empty_tags() -> None:
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(
            {
                "id": "bad",
                "title": "Bad",
                "statement": "x",
                "role": "backend",
                "seniority": "junior",
                "difficulty": "junior",
                "tags": [],
                "languages": ["python"],
                "tests": [{"id": "a", "input": "", "expected_output": ""}],
            }
        )


def test_schema_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        ProblemSpec.model_validate(
            {
                "id": "bad",
                "title": "Bad",
                "statement": "x",
                "role": "backend",
                "seniority": "junior",
                "difficulty": "junior",
                "tags": ["python"],
                "languages": ["python"],
                "tests": [{"id": "a", "input": "", "expected_output": ""}],
                "limits": {"timeout_ms": 0, "memory_mb": 128},
            }
        )


def test_schema_rejects_duplicate_test_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate test id"):
        ProblemSpec.model_validate(
            {
                "id": "bad",
                "title": "Bad",
                "statement": "x",
                "role": "backend",
                "seniority": "junior",
                "difficulty": "junior",
                "tags": ["python"],
                "languages": ["python"],
                "tests": [
                    {"id": "a", "input": "1", "expected_output": "1"},
                    {"id": "a", "input": "2", "expected_output": "2"},
                ],
            }
        )


def test_loader_rejects_malformed_yaml(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "broken", "id: [\n")
    with pytest.raises(ProblemCatalogInvalidError, match="Malformed YAML"):
        ProblemLoader(tmp_path).load()


def test_loader_rejects_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    with pytest.raises(ProblemCatalogNotFoundError, match="does not exist"):
        ProblemLoader(missing).load()


def test_loader_rejects_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(ProblemCatalogEmptyError, match="empty"):
        ProblemLoader(tmp_path).load()


def test_loader_rejects_duplicate_ids(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "sample-problem", VALID_YAML)
    (tmp_path / "sample-problem.yml").write_text(
        VALID_YAML.replace("title: Sample", "title: Copy"),
        encoding="utf-8",
    )
    with pytest.raises(ProblemCatalogInvalidError, match="Duplicate problem id"):
        ProblemLoader(tmp_path).load()


def test_loader_rejects_stem_mismatch(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "wrong-name", VALID_YAML)
    with pytest.raises(ProblemCatalogInvalidError, match="stem must match id"):
        ProblemLoader(tmp_path).load()


def test_loader_reports_invalid_field(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path,
        "sample-problem",
        VALID_YAML.replace("seniority: junior", "seniority: intern"),
    )
    with pytest.raises(ProblemCatalogInvalidError, match="seniority"):
        ProblemLoader(tmp_path).load()
