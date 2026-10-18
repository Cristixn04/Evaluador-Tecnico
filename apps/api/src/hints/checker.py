"""Detector de inactividad para Progressive Hints.

Determina cuándo un candidato está lo suficientemente inactivo en la fase
CODING para merecer una hint, basándose en Turns y Snapshot ya persistidos
en la base de datos.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.db.enums import InterviewPhase, TurnSpeaker
from src.db.models import Interview
from src.hints.thresholds import get_threshold


def _get_last_candidate_turn_created_at(interview: Interview) -> datetime | None:
    """Obtener el created_at del último turno del candidato."""
    last_candidate = None
    for turn in interview.turns:
        if turn.speaker == TurnSpeaker.CANDIDATE and (
            last_candidate is None or turn.created_at > last_candidate.created_at
        ):
            last_candidate = turn
    if last_candidate is None:
        return None
    return last_candidate.created_at


def _get_last_snapshot_created_at(interview: Interview) -> datetime | None:
    """Obtener el created_at del último snapshot."""
    last_snapshot = None
    for snap in interview.snapshots:
        if last_snapshot is None or snap.created_at > last_snapshot.created_at:
            last_snapshot = snap
    if last_snapshot is None:
        return None
    return last_snapshot.created_at


def _compute_last_activity(interview: Interview) -> datetime | None:
    """Determinar la última actividad como el timestamp más reciente
    entre el último Turn CANDIDATE y el último Snapshot."""
    last_turn_ts = _get_last_candidate_turn_created_at(interview)
    last_snap_ts = _get_last_snapshot_created_at(interview)

    candidates = [ts for ts in [last_turn_ts, last_snap_ts] if ts is not None]
    if not candidates:
        return None
    return max(candidates)


def _is_eligible_for_hint(interview: Interview, hint_level: int) -> bool:
    """Determinar si una entrevista es elegible para recibir la próxima hint.

    Condiciones:
    - fase debe ser CODING
    - hint_level < 3 (máximo 3 niveles)
    - debe haber nueva actividad desde la última hint entregada
    - la inactividad debe superar el threshold correspondiente
    """
    if interview.phase != InterviewPhase.CODING:
        return False

    if hint_level >= 3:
        return False

    # La actividad nueva debe haber ocurrido después de last_hint_at
    if interview.last_hint_at is not None:
        last_activity = _compute_last_activity(interview)
        if last_activity is None:
            # No hay actividad previa; si hint_level es 0, podemos considerar
            # que es elegible (primer hint). Si hint_level > 0, requiere
            # que haya habido actividad después de la última hint.
            return hint_level == 0

        # La actividad nueva debe ser después de last_hint_at
        activity_after_last_hint = last_activity > interview.last_hint_at
        if not activity_after_last_hint:
            # El candidato no ha tenido actividad nueva desde la última hint
            return False

    # Calcular inactivity desde la última actividad (o desde last_hint_at si no hay nueva)
    # Usamos la actividad más reciente o last_hint_at como referencia
    reference_ts = _compute_last_activity(interview)
    if reference_ts is None:
        # No hay actividad previa; para hint_level=0, elegible de inmediato
        # para hint_level>0, requiere actividad previa
        return hint_level == 0

    inactivity_seconds = (datetime.now(UTC) - reference_ts).total_seconds()
    threshold = get_threshold(hint_level)

    return inactivity_seconds > threshold


def check_hint_eligibility(interview: Interview, hint_level: int | None = None) -> bool:
    """Verificar si la entrevista está lista para recibir la próxima hint.

    Si hint_level es None, se usa el hint_level actual de la entrevista.
    """
    level = hint_level if hint_level is not None else interview.hint_level
    return _is_eligible_for_hint(interview, level)
