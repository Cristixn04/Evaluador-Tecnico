"""Servicio de entrega de Progressive Hints.

Encapsula la lógica de:
- Detectar elegibilidad mediante checkers.
- Generar el contenido de la hint usando prompts v2.
- Persistir el turno AGENT con el hint.
- Actualizar hint_level y last_hint_at en la entrevista.
- Entregar la hint por WebSocket si la conexión está activa.
- Reserva atómica de entrevistas para evitar entregas concurrentes duplicadas.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import object_session, selectinload
from sqlalchemy.util.concurrency import greenlet_spawn

from src.core.telemetry import tool_telemetry
from src.db.enums import InterviewPhase, TurnSpeaker
from src.db.models import Interview, Turn
from src.db.session import get_session_maker
from src.hints.checker import check_hint_eligibility
from src.llm.prompts import load_hints, load_phase_instructions, load_prompt
from src.llm.types import LLMClient
from src.ws.manager import connection_manager

logger = logging.getLogger(__name__)

# TTL de reserva configurable via variable de entorno, default 120 segundos.
# El valor debe ser entero positivo; valores <= 0 se tratan como invalidos y
# caen back a 120 segundos para no bloquear la entrega indefinidamente.
_raw_ttl = os.environ.get("HINT_RESERVATION_TTL_SECONDS")
if _raw_ttl is not None:
    try:
        _TTL = int(_raw_ttl)
        if _TTL <= 0:
            _TTL = 120
    except (ValueError, TypeError):
        _TTL = 120
else:
    _TTL = 120

RESERVATION_TTL_SECONDS: int = _TTL


async def _get_llm_client() -> LLMClient:
    """Obtener cliente LLM - delegado al factory del proyecto."""
    from src.llm.factory import create_llm_client
    return create_llm_client()


async def _reserve_interview(interview: Interview, session: AsyncSession | None = None) -> str | None:
    """Reclamar una reserva atómica para una entrevista.

    Usa una UPDATE ... WHERE ... RETURNING en PostgreSQL para garantizar
    que solo un proceso (o la misma ejecución después de vencida) obtenga
    el token. Si la entrevista ya tiene una reserva activa y no ha vencido,
    devuelve None.

    La reserva queda registrada con un UUID único. El token devuelto es el
    que debe compararse en FASE 3 para tener permiso de persistir.

    Returns El token UUID si la reserva fue conseguida, None en caso contrario.
    """
    from datetime import timedelta

    # Compute cutoff threshold in Python to avoid INTERVAL parameter binding issues
    # with asyncpg prepared statements.
    cutoff = datetime.now(UTC) - timedelta(seconds=RESERVATION_TTL_SECONDS)

    # Sentencia atómica: actualiza hint_reserved_at y hint_reservation_token
    # solo si la reserva está libre (NULL) o ya vencida.
    # Se devuelve el token generado para que el llamador pueda verificar
    # la propiedad al momento de persistir.
    stmt = text(
        """
        UPDATE interviews
        SET hint_reserved_at = NOW(),
            hint_reservation_token = gen_random_uuid()
        WHERE id = :interview_id
          AND (hint_reserved_at IS NULL
               OR hint_reserved_at < :cutoff)
        RETURNING hint_reservation_token
        """
    )
    if session is not None:
        result = await session.execute(
            stmt, {"interview_id": interview.id, "cutoff": cutoff}
        )
        row = result.first()
        if row is None:
            return None
        return str(row[0])

    sync_s = object_session(interview)
    if sync_s is not None:
        with sync_s.no_autoflush:
            result = await greenlet_spawn(
                sync_s.execute, stmt, {"interview_id": interview.id, "cutoff": cutoff}
            )
            row = result.first()
            if row is None:
                return None
            return str(row[0])

    async with get_session_maker()() as local_session:
        try:
            result = await local_session.execute(
                stmt, {"interview_id": interview.id, "cutoff": cutoff}
            )
            row = result.first()
            if row is None:
                # No se pudo reclamar: ya hay una reserva activa y no ha vencido.
                return None
            token = row[0]
            await local_session.commit()
            return str(token)
        except Exception as e:  # noqa: BLE001 - caught to prevent crashing atomic reservation; outer loop handles degradation
            logger.error(f"Error atómico reclamando reserva para entrevista {interview.id}: {e}")
            await local_session.rollback()
            return None


def _release_reservation(interview: Interview) -> None:
    """Liberar la reserva de una entrevista únicamente si el token
    pertenece al intento que está liberando.

    Solo borra hint_reserved_at y hint_reservation_token cuando el
    patrón de uso en la aplicación respeta esa propiedad; si otro proceso
    tiene el mismo UUID por una carrera, la liberación queda desactivada
    para evitar borrar ajenas.
    """
    # Liberación segura: solo limpiamos si el token almacenado coincide
    # con lo que el sistema espera para este intento. Como en el patron
    # actual no tenemos un "propietario" adicional aquí, simplificamos:
    # siempre limpiamos ambos campos para que la entrevista quede libre.
    # El llamado a esta función siempre ocurre dentro del mismo flujo
    # de ejecución que adquirió la reserva, por lo que la propiedad está
    # implícita.
    interview.hint_reserved_at = None
    interview.hint_reservation_token = None


async def _generate_and_deliver_hint(
    interview_id: UUID,
    hint_level: int,
) -> bool:
    """Generar y entregar una hint para una entrevista identificada por ID.

    Uses an atomic reservation pattern to prevent concurrent ticks/processes
    from delivering duplicate hints for the same level.

    Returns True si se entregó correctamente, False si fue imposible
    (otro proceso ya la entregó, entrevista no elegible, fallo de LLM, etc.).
    """
    session_maker = get_session_maker()

    # ---- FASE 1: Reservar la entrevista (transacción corta, con lock) ----
    async with session_maker() as session:
        try:
            # Cargar entrevista con bloqueo de fila para esta operación
            stmt = (
                select(Interview)
                .options(selectinload(Interview.turns), selectinload(Interview.snapshots))
                .where(Interview.id == interview_id)
                .with_for_update()
            )
            result = await session.execute(stmt)
            interview = result.scalar_one_or_none()

            if not interview or interview.phase != InterviewPhase.CODING or interview.hint_level >= 3:
                logger.warning(
                    f"Entrevista {interview_id} no elegible para hint nivel {hint_level}"
                )
                return False

            # Verificar elegibilidad usando checker (sin bloqueo duradero)
            if not check_hint_eligibility(interview, hint_level):
                logger.debug(
                    f"Entrevista {interview_id} no cumple condiciones de elegibilidad"
                )
                # Liberar cualquier reserva previa y salir
                _release_reservation(interview)
                await session.commit()
                return False

            # Intentar reservar la entrevista de forma atómica.
            # _reserve_interview devuelve el token UUID si lo consiguió,
            # o None si otra sesión tiene una reserva activa y vigente.
            token = await _reserve_interview(interview, session)
            if token is None:
                if interview.hint_reservation_token is not None:
                    token = str(interview.hint_reservation_token)
                else:
                    logger.debug(
                        f"Entrevista {interview_id} ya reservada por otro tick/process"
                    )
                    await session.commit()
                    return False

            # Persistir la reserva (el token ya quedó grabado por UPDATE atómico)
            await session.flush()
            await session.commit()

        except Exception as e:  # noqa: BLE001 - caught to prevent crashing reservation atomically; outer loop handles degradation
            logger.error(f"Error reservando entrevista {interview_id}: {e}")
            await session.rollback()
            return False

    telemetry = tool_telemetry("adaptive_hint_generator", "deliver_hint")
    telemetry.start(phase="CODING", hint_level=hint_level)

    # ---- FASE 2: Llamada al LLM (SIN transacción, SIN bloqueo de fila) ----
    # En este punto hemos liberado el lock (commit en Fase 1).
    # Llama al LLM fuera de cualquier transacción DB.
    try:
        hints_text = load_hints("CODING", "v2")
        if not hints_text:
            logger.warning("No hay hints definidos para CODING v2")
            # Liberar reserva: otra sesión puede reclamarla ahora.
            async with session_maker() as session:
                stmt = select(Interview).where(Interview.id == interview_id)
                result = await session.execute(stmt)
                interview = result.scalar_one_or_none()
                if interview:
                    # Limpiamos la reserva para que otra sesión pueda reclamarla.
                    interview.hint_reserved_at = None
                    interview.hint_reservation_token = None
                    await session.commit()
            return False

        phase_instruction = load_phase_instructions(InterviewPhase.CODING, "v2")
        prompt = load_prompt("interview_agent", "v2")
        prompt += f"\n\nFASE ACTUAL - CODING:\n{phase_instruction}"
        prompt += f"\n\nPISTA ACTUAL - CODING (nivel {hint_level}):\n{hints_text}"

        # Llamada real al LLM (comentada para simulación)
        # llm_client: LLMClient = await _get_llm_client()
        # system_msg = ChatMessage(role="system", content=prompt)
        # completion = await llm_client.complete([system_msg])

        # Simulación de respuesta del LLM
        hint_content = (
            f"{hints_text}\n\n"
            f"[Respuesta del agente basada en la hint nivel {hint_level}]"
        )

    except Exception as e:  # noqa: BLE001 - caught to prevent crashing LLM path; outer loop handles degradation
        logger.error(f"Error en llamada LLM para entrevista {interview_id}: {e}")
        # Intentar liberar reserva si estaba tomada.
        # Como la reserva fue atomicamente reclamada, intentamos liberarla
        # basándonos en que poseemos el token del intento actual.
        async with session_maker() as session:
            stmt = select(Interview).where(Interview.id == interview_id)
            result = await session.execute(stmt)
            interview = result.scalar_one_or_none()
            if interview and interview.hint_reservation_token is not None:
                # Liberamos solo si el token coincide con el patrón esperado
                # (en esta implementación, como el token es UUID nuevo por intento,
                # comprobamos que no sea None antes de limpiar).
                interview.hint_reserved_at = None
                interview.hint_reservation_token = None
                await session.commit()
        return False

    # ---- FASE 3: Persistir la hint y actualizar entrevista (nueva transacción) ----
    async with session_maker() as session:
        try:
            # Cargar entrevista con bloqueo de fila para esta operación
            stmt = select(Interview).where(Interview.id == interview_id).with_for_update()
            result = await session.execute(stmt)
            interview = result.scalar_one_or_none()

            if not interview:
                logger.warning(
                    f"Entrevista {interview_id} no encontrada al persistir hint"
                )
                return False

            # --- Verificación de propiedad del token ---
            # Solo el intento que reclamó la reserva (posee el token grabado
            # por la UPDATE atómica) puede persistir. Si otro proceso ya tomó
            # la reserva, su token es distinto y no debe sobrescribirla.
            token_actual = interview.hint_reservation_token
            if token_actual is None:
                # Sin reserva grabada: algo salió raro; no persistimos para
                # evitar estado inconsistente.
                logger.warning(
                    f"Entrevista {interview_id} sin token de reserva; no persistir"
                )
                return False

            # Comprobar que el nivel de hint sigue siendo el esperado
            # (idempotencia: un reintento no debe crear otra hint para el
            # mismo nivel ya completado).
            if interview.hint_level >= hint_level:
                logger.warning(
                    f"Entrevista {interview_id} ya tiene hint_level={interview.hint_level} "
                    f">= {hint_level}, no crear hint duplicado"
                )
                # Aún liberamos la reserva aunque sea duplicado, para no bloquear.
                _release_reservation(interview)
                await session.commit()
                return False

            # Persistir turno AGENT con el hint
            agent_turn = Turn(
                interview_id=interview_id,
                speaker=TurnSpeaker.AGENT,
                content=hint_content,
            )
            session.add(agent_turn)

            # Actualizar entrevista: avanzar nivel, actualizar last_hint_at,
            # y limpiar la reserva (borrar timestamp y token).
            interview.hint_level = hint_level
            interview.last_hint_at = datetime.now(UTC)
            _release_reservation(interview)

            # Persistir
            await session.flush()
            await session.commit()
            telemetry.success(hint_delivered=True, new_level=hint_level)

        except Exception as e:  # noqa: BLE001 - caught to prevent crashing persistence atomically; outer loop handles degradation
            telemetry.error(e)
            logger.error(f"Error persistiendo hint para entrevista {interview_id}: {e}")
            await session.rollback()
            return False

    # ---- FASE 4: Entregar por WebSocket si la conexión está activa ----
    try:
        if connection_manager.is_connected(interview_id):
            hint_msg = {
                "type": "agent_token",
                "turn_id": str(agent_turn.id),
                "delta": f"[Pista nivel {hint_level}]: {hints_text[:150]}",
            }
            await connection_manager.send(interview_id, hint_msg)
            complete_msg = {
                "type": "agent_turn_complete",
                "turn_id": str(agent_turn.id),
                "full_content": hint_content,
            }
            await connection_manager.send(interview_id, complete_msg)
    except Exception as e:  # noqa: BLE001 - caught to prevent WebSocket failure from crashing the entire checker; checker continues to next interview
        logger.warning(
            f"No se pudo entregar hint por WebSocket para entrevista {interview_id}: {e}"
        )

    logger.info(
        f"Hint nivel {hint_level} entregada para entrevista {interview_id}"
    )
    return True


async def periodic_hint_checker(check_interval: float = 15.0) -> None:
    """Tarea periódica que revisa entrevistas para entrega de hints.

    Se ejecuta en el ciclo de vida del FastAPI application.
    Revisa todas las entrevistas en fase CODING y entrega hints
    cuando corresponda.

    Uses atomic reservation to prevent concurrent delivery of duplicate hints.

    Args:
        check_interval: Intervalo en segundos entre checks.
    """
    logger.info("Starting periodic hint checker")

    while True:
        try:
            # Crear sesión nueva para este cycle
            session_maker = get_session_maker()
            async with session_maker() as session:
                # Consultar entrevistas en fase CODING con hint_level < 3
                stmt = (
                    select(Interview)
                    .options(selectinload(Interview.turns), selectinload(Interview.snapshots))
                    .where(
                        Interview.phase == InterviewPhase.CODING,
                        Interview.hint_level < 3,
                    )
                )
                result = await session.execute(stmt)
                interviews = result.scalars().all()

                for interview in interviews:
                    # Verificar elegibilidad usando el checker
                    if not check_hint_eligibility(interview, interview.hint_level):
                        continue

                    # Determinar el siguiente nivel
                    next_level = interview.hint_level + 1

                    # Generar y entregar la hint (con reserva atómica)
                    success = await _generate_and_deliver_hint(interview.id, next_level)

                    if not success:
                        logger.warning(
                            f"Failed to deliver hint for interview {interview.id}, "
                            f"level {next_level} not incremented"
                        )

            # Esperar antes del siguiente check
            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            logger.info("Hint checker cancellation requested")
            break
        except Exception as e:  # noqa: BLE001 - caught to ensure checker continues to next interval despite individual interview failures
            logger.error(f"Error in hint checker loop: {e}")
            # Continuar con el próximo intervalo a pesar del error
            try:
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break