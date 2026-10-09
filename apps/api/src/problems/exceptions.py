from pathlib import Path


class ProblemCatalogError(Exception):
    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path


class ProblemCatalogNotFoundError(ProblemCatalogError):
    pass


class ProblemCatalogEmptyError(ProblemCatalogError):
    pass


class ProblemCatalogInvalidError(ProblemCatalogError):
    pass
