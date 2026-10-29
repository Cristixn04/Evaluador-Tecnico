from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.telemetry import tool_telemetry
from src.db.enums import InterviewPhase, TurnSpeaker
from src.db.models import Interview, Turn
from src.interview.service import InterviewService
from src.llm.factory import create_llm_client, get_llm_client  # noqa: F401
from src.llm.prompts import load_hints, load_phase_instructions, load_prompt
from src.llm.sanitizer import wrap_untrusted_input
from src.llm.types import ChatMessage, LLMClient
from src.problems.selector import ProblemSelector

if TYPE_CHECKING:
    from src.db.models import Problem, Vacancy


# Umbrales de inactividad para entrega de hints (en segundos)
# Definidos basándose en los archivos de hints v2:
#   Nivel 1: >3 min sin output o progreso
#   Nivel 2: >5 min o errores recurrentes en tests
#   Nivel 3: >10 min o frustración detectada
HINT_THRESHOLDS_SECONDS = [180, 300, 600]  # 3min, 5min, 10min


class InterviewAgent:
    def __init__(
        self,
        session: AsyncSession,
        interview_service: InterviewService,
        problem_selector: ProblemSelector,
        prompt_version: str = "v1",
        llm_client: LLMClient | None = None,
    ) -> None:
        self._session = session
        self._interview_service = interview_service
        self._problem_selector = problem_selector
        self._prompt_version = prompt_version
        self._llm_client = llm_client
        self._owns_llm_client = llm_client is None
        self._system_prompt_template = load_prompt("interview_agent", self._prompt_version)

    async def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = create_llm_client()
            self._owns_llm_client = True
        return self._llm_client

    async def aclose(self) -> None:
        """Cerrar recursos del cliente LLM de forma limpia e idempotente."""
        if self._owns_llm_client and self._llm_client is not None:
            client = self._llm_client
            self._llm_client = None
            await client.aclose()

    async def stream_response(
        self,
        interview_id: UUID,
        user_message: str,
        auto_hints: bool = False,
    ) -> AsyncGenerator[str, None]:
        """Stream agent response tokens."""
        # Load interview with related data
        interview = await self._session.get(Interview, interview_id)
        if not interview:
            return

        # Load vacancy and problem
        from src.db.models import Problem, Vacancy
        vacancy = await self._session.get(Vacancy, interview.vacancy_id)
        problem = await self._session.get(Problem, interview.problem_id) if interview.problem_id else None

        # Get recent turns for context
        from sqlalchemy import select
        result = await self._session.scalars(
            select(Turn)
            .where(Turn.interview_id == interview_id)
            .order_by(Turn.created_at.desc())
            .limit(10)
        )
        recent_turns = list(reversed(result.all()))

        # Determine current phase for prompt building
        current_phase = interview.phase if hasattr(interview, 'phase') else InterviewPhase.INTRO

        # Check if we should deliver a hint based on inactivity
        hint_delivered = False
        if auto_hints and current_phase == InterviewPhase.CODING:
            hint_delivered = await self._maybe_deliver_hint(interview, current_phase)

        # Build system prompt using versioned prompt
        system_prompt = self._build_system_prompt(
            vacancy, problem, current_phase, auto_hints, hint_delivered, interview.hint_level
        )

        messages = [ChatMessage(role="system", content=system_prompt)]

        # Identificar si el turno más reciente en BD es el turno sin responder del candidato
        unreplied_turn_id = None
        if recent_turns and recent_turns[-1].speaker == TurnSpeaker.CANDIDATE:
            unreplied_turn_id = recent_turns[-1].id

        for turn in recent_turns:
            # Excluir avisos y transiciones internas del contexto conversacional del LLM
            if turn.speaker == TurnSpeaker.AGENT and turn.content.startswith("Phase transitioned to "):
                continue

            # Evitar duplicar el mensaje del candidato que ya fue persistido por _handle_chat
            if turn.id == unreplied_turn_id:
                continue

            if turn.speaker == TurnSpeaker.AGENT:
                messages.append(ChatMessage(role="assistant", content=turn.content))
            else:
                # Sanitizar y delimitar turnos previos del candidato para defensa de injection (S-17)
                messages.append(ChatMessage(role="user", content=wrap_untrusted_input(turn.content)))

        # Add current user message - wrap in untrusted tags for prompt injection defense (S-17)
        messages.append(ChatMessage(role="user", content=wrap_untrusted_input(user_message)))

        # Stream response
        llm_client = await self._get_llm_client()
        full_response = ""

        async for chunk in self._stream_llm(llm_client, messages):
            full_response += chunk
            yield chunk

        # Persist agent turn
        agent_turn = Turn(
            interview_id=interview_id,
            speaker=TurnSpeaker.AGENT,
            content=full_response,
        )
        self._session.add(agent_turn)
        await self._session.flush()

    def _get_last_candidate_turn_created_at(self, interview: Interview) -> float | None:
        """Obtener el created_at del último turno del candidato."""
        last_candidate = None
        for turn in interview.turns:
            if turn.speaker == TurnSpeaker.CANDIDATE and (last_candidate is None or turn.created_at > last_candidate.created_at):
                last_candidate = turn
        if last_candidate is None:
            return None
        return last_candidate.created_at.timestamp()

    async def _maybe_deliver_hint(self, interview: Interview, phase: InterviewPhase) -> bool:
        """Determinar y entregar la próxima hint si corresponde.

        Lógica:
        1. Si hint_level >= 3, no entregar más hints
        2. Calcular inactivity desde el último turno del candidato
        3. Si la inactividad supera el threshold, entregar el siguiente hint
        4. Incrementar hint_level y actualizar last_hint_at
        5. Persistir el cambio
        """
        # Nivel máximo alcanzado
        if interview.hint_level >= 3:
            return False

        # Obtener tiempo desde último mensaje del candidato
        last_candidate_ts = self._get_last_candidate_turn_created_at(interview)
        now_ts = time.time()

        if last_candidate_ts is None:
            # Sin mensajes previos del candidato - no activar hint todavía
            return False

        inactivity_seconds = now_ts - last_candidate_ts

        # Verificar si la inactividad supera el threshold para el nivel actual
        threshold = HINT_THRESHOLDS_SECONDS[interview.hint_level]
        if inactivity_seconds <= threshold:
            return False

        telemetry = tool_telemetry("adaptive_hint_generator", "deliver_hint")
        telemetry.start(
            phase=phase.value,
            inactivity_sec=round(inactivity_seconds, 1),
            current_level=interview.hint_level,
        )
        try:
            # Entregar el siguiente hint
            next_level = interview.hint_level + 1
            interview.hint_level = next_level
            interview.last_hint_at = datetime.now(UTC)

            # Persistir el cambio
            self._session.add(interview)
            await self._session.flush()

            telemetry.success(
                hint_delivered=True,
                new_level=next_level,
            )
            return True
        except Exception as exc:
            await self._session.rollback()
            telemetry.error(exc)
            raise

    def _build_system_prompt(
        self,
        vacancy: Vacancy | None,
        problem: Problem | None,
        phase: InterviewPhase,
        auto_hints: bool,
        hint_delivered: bool,
        hint_level: int,
    ) -> str:
        """Build system prompt based on vacancy, problem, and current phase using versioned prompts."""

        # Load phase instructions from versioned prompt
        phase_instruction = load_phase_instructions(phase.value, self._prompt_version)

        # Load progressive hints context - solo la hint actual, no todas
        hints_context = ""
        if auto_hints and phase == InterviewPhase.CODING and hint_delivered:
            # Cargar solo la hint del nivel actual
            hints_text = load_hints(phase.value, self._prompt_version)
            if hints_text:
                # Inyectamos la hint completa del nivel correspondiente
                hints_context = f"\n\nPISTA ACTUAL - CODING (nivel {hint_level}):\n{hints_text}"

        # Build the full prompt from the versioned template
        prompt = self._system_prompt_template

        # Append vacancy profile if available
        if vacancy and vacancy.profile:
            skills = vacancy.profile.get("required_skills", [])
            if skills:
                prompt += f"\n\nHABILIDADES REQUERIDAS: {', '.join(skills)}"

        # Append problem if available
        if problem:
            prompt += f"\n\nPROBLEMA ASIGNADO:\n{problem.scenario_preview}"

        # Append phase-specific instructions from versioned prompt
        if phase_instruction:
            prompt += f"\n\nFASE ACTUAL - {phase.value}:\n{phase_instruction}"

        # Directiva de Anti-Cheat Cognitivo para fase PROBE
        if phase == InterviewPhase.PROBE:
            prompt += (
                "\n\nDIRECTIVA ANTI-CHEAT COGNITIVO (FASE PROBE):\n"
                "Formula preguntas reflexivas y profundas sobre el código escrito por el candidato. "
                "Exige justificar la complejidad computacional temporal y espacial O(), "
                "la razón de las estructuras de datos seleccionadas y cómo su implementación mitiga casos de borde. "
                "Esto expone de forma ética e indiscutible si el candidato comprende su propio código o si fue copiado."
            )

        # Append progressive hints context
        if hints_context:
            prompt += hints_context

        return prompt

    async def _stream_llm(self, client: LLMClient, messages: list[ChatMessage]) -> AsyncGenerator[str, None]:
        """Stream response from LLM."""
        # For now, use a simple completion and yield chunks
        # In a real implementation, this would use the streaming API
        completion = await client.complete(messages)
        # Simulate streaming by yielding words
        words = completion.content.split()
        for i, word in enumerate(words):
            if i == 0:
                yield word
            else:
                yield " " + word