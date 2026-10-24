import pytest

from src.llm.prompts import (
    PromptNotFoundError,
    get_active_prompt_version,
    load_hints,
    load_phase_instructions,
    load_prompt,
)


class TestLoadPrompt:
    def test_load_prompt_v1(self):
        p = load_prompt("interview_agent", "v1")
        assert isinstance(p, str)
        assert len(p) > 0

    def test_load_prompt_v2(self):
        p = load_prompt("interview_agent", "v2")
        assert isinstance(p, str)
        assert len(p) > 0

    def test_load_prompt_defaults_to_v1(self):
        p = load_prompt("interview_agent")
        assert isinstance(p, str)
        assert len(p) > 0

    def test_load_prompt_rejects_unsupported_version(self):
        with pytest.raises(PromptNotFoundError):
            load_prompt("interview_agent", "v3")

    def test_load_prompt_rejects_nonexistent(self):
        with pytest.raises(PromptNotFoundError):
            load_prompt("nonexistent", "v2")


class TestLoadPhaseInstructions:
    @pytest.mark.parametrize("phase", [
        "INTRO", "PROBLEM", "CLARIFY", "DESIGN", "CODING", "PROBE", "WRAPUP", "EVALUATE"
    ])
    def test_load_phase_instructions_v2(self, phase):
        instr = load_phase_instructions(phase, "v2")
        assert isinstance(instr, str)
        assert len(instr) > 0
        assert phase in instr.upper()

    def test_load_phase_instructions_v1_returns_content(self):
        # v1 prompt is a single file; phase instructions extracted from it
        instr = load_phase_instructions("CODING", "v1")
        assert isinstance(instr, str)

    def test_load_phase_instructions_returns_empty_for_missing(self):
        instr = load_phase_instructions("NONEXISTENT", "v2")
        assert instr == ""


class TestLoadHints:
    def test_load_hints_coding_v2(self):
        hints = load_hints("CODING", "v2")
        assert isinstance(hints, str)
        assert len(hints) > 0

    def test_load_hints_returns_empty_when_no_file(self):
        hints = load_hints("NONEXISTENT", "v2")
        assert hints == ""

    def test_load_hints_coding_v1_returns_empty(self):
        # v1 does not have modular hint files
        hints = load_hints("CODING", "v1")
        assert hints == ""


class TestGetActivePromptVersion:
    def test_get_active_prompt_version(self):
        version = get_active_prompt_version()
        assert version == "v2"


class TestPromptVersionSelection:
    def test_v1_and_v2_both_loadable(self):
        v1 = load_prompt("interview_agent", "v1")
        v2 = load_prompt("interview_agent", "v2")
        assert len(v1) > 0
        assert len(v2) > 0
        # v1 and v2 should be different
        assert v1 != v2

    def test_v1_has_phase_instructions(self):
        # v1 prompt is a single file; phase instructions may be extracted
        instr = load_phase_instructions("CODING", "v1")
        assert isinstance(instr, str)

    def test_v2_has_phase_instructions(self):
        instr = load_phase_instructions("CODING", "v2")
        assert isinstance(instr, str)
        assert len(instr) > 0

    def test_v2_hints_available(self):
        hints = load_hints("CODING", "v2")
        assert isinstance(hints, str)
        assert len(hints) > 0