from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


class PromptNotFoundError(LookupError):
    pass


def get_active_prompt_version() -> str:
    """Retorna la versión activa de prompts del sistema."""
    return "v2"


@lru_cache(maxsize=32)
def load_prompt(name: str, version: str = "v1") -> str:
    path = PROMPTS_ROOT / version / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(f"Prompt {version}/{name} was not found")
    return path.read_text(encoding="utf-8").strip()


def _extract_phase_section(content: str, phase_name: str) -> str:
    """Extrae el bloque markdown correspondiente a una fase técnica."""
    lines = content.splitlines()
    in_section = False
    section_lines: list[str] = []
    section_level = 0

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_hashes = len(line) - len(line.lstrip("#"))
            heading_text = line.lstrip("#").strip()

            if in_section:
                if heading_hashes <= section_level:
                    break
                section_lines.append(line)
            elif phase_name in heading_text.upper():
                in_section = True
                section_level = heading_hashes
                section_lines.append(line)
        elif in_section:
            section_lines.append(line)

    return "\n".join(section_lines).strip()


@lru_cache(maxsize=32)
def load_phase_instructions(phase: Any, version: str = "v2") -> str:
    """Carga las instrucciones específicas para una fase de la entrevista."""
    phase_name = getattr(phase, "value", str(phase)).upper()

    # Primero intentar archivo modular de fases
    phases_file = PROMPTS_ROOT / version / "interview_agent_phases.md"
    if not phases_file.is_file():
        # Fallback para versiones mono-archivo (ej: v1)
        phases_file = PROMPTS_ROOT / version / "interview_agent.md"

    if not phases_file.is_file():
        return ""

    content = phases_file.read_text(encoding="utf-8")
    return _extract_phase_section(content, phase_name)


@lru_cache(maxsize=32)
def load_hints(phase: Any, version: str = "v2") -> str:
    """Carga pistas progresivas para la fase especificada."""
    phase_str = getattr(phase, "value", str(phase)).lower()
    hints_file = PROMPTS_ROOT / version / "hints" / f"{phase_str}.md"
    if not hints_file.is_file():
        return ""
    return hints_file.read_text(encoding="utf-8").strip()
