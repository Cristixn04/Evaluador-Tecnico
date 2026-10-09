from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError
from yaml import YAMLError

from src.problems.exceptions import (
    ProblemCatalogEmptyError,
    ProblemCatalogInvalidError,
    ProblemCatalogNotFoundError,
)
from src.problems.schemas import ProblemSpec

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[4] / "problems"


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


class ProblemLoader:
    def __init__(self, catalog_dir: Path) -> None:
        self.catalog_dir = catalog_dir
        self._cache: tuple[ProblemSpec, ...] | None = None

    def load(self) -> tuple[ProblemSpec, ...]:
        if self._cache is None:
            self._cache = self._read_catalog()
        return self._cache

    def reload(self) -> tuple[ProblemSpec, ...]:
        self._cache = None
        return self.load()

    def get(self, problem_id: str) -> ProblemSpec:
        for spec in self.load():
            if spec.id == problem_id:
                return spec
        raise ProblemCatalogInvalidError(
            f"Problem {problem_id!r} was not found in catalog",
            path=self.catalog_dir,
        )

    def _read_catalog(self) -> tuple[ProblemSpec, ...]:
        catalog_dir = self.catalog_dir
        if not catalog_dir.exists():
            raise ProblemCatalogNotFoundError(
                f"Problem catalog directory does not exist: {catalog_dir}",
                path=catalog_dir,
            )
        if not catalog_dir.is_dir():
            raise ProblemCatalogNotFoundError(
                f"Problem catalog path is not a directory: {catalog_dir}",
                path=catalog_dir,
            )

        files = sorted(
            path
            for path in catalog_dir.iterdir()
            if path.is_file()
            and path.suffix in {".yaml", ".yml"}
            and not path.name.startswith(".")
        )
        if not files:
            raise ProblemCatalogEmptyError(
                f"Problem catalog is empty: {catalog_dir}",
                path=catalog_dir,
            )

        specs: list[ProblemSpec] = []
        seen_ids: dict[str, Path] = {}
        for path in files:
            spec = self._load_file(path)
            previous = seen_ids.get(spec.id)
            if previous is not None:
                raise ProblemCatalogInvalidError(
                    f"Duplicate problem id {spec.id!r} in {path.name} "
                    f"(already defined in {previous.name})",
                    path=path,
                )
            seen_ids[spec.id] = path
            specs.append(spec)

        return tuple(sorted(specs, key=lambda item: item.id))

    def _load_file(self, path: Path) -> ProblemSpec:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProblemCatalogInvalidError(
                f"Cannot read problem file {path.name}: {exc}",
                path=path,
            ) from exc

        try:
            payload: Any = yaml.safe_load(raw)
        except YAMLError as exc:
            raise ProblemCatalogInvalidError(
                f"Malformed YAML in {path.name}: {exc}",
                path=path,
            ) from exc

        if not isinstance(payload, dict):
            raise ProblemCatalogInvalidError(
                f"Problem file {path.name} must contain a YAML object",
                path=path,
            )

        try:
            spec = ProblemSpec.model_validate(payload)
        except ValidationError as exc:
            raise ProblemCatalogInvalidError(
                f"Invalid problem in {path.name}: {_format_validation_error(exc)}",
                path=path,
            ) from exc

        if path.stem != spec.id:
            raise ProblemCatalogInvalidError(
                f"Problem file {path.name} stem must match id {spec.id!r}",
                path=path,
            )
        return spec


def load_default_catalog() -> tuple[ProblemSpec, ...]:
    return ProblemLoader(DEFAULT_CATALOG_DIR).load()
