from functools import lru_cache
from pathlib import Path

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


class PromptNotFoundError(LookupError):
    pass


@lru_cache(maxsize=32)
def load_prompt(name: str, version: str = "v1") -> str:
    path = PROMPTS_ROOT / version / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"Prompt {version}/{name} was not found")
    return path.read_text(encoding="utf-8").strip()
