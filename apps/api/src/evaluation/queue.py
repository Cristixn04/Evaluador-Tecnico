"""Módulo de encolado durable y seguimiento de evaluaciones con Redis y ARQ (S-14)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import types
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import redis.asyncio as aioredis
from redis.exceptions import RedisError

try:
    from arq import create_pool  # type: ignore[import-not-found]
    from arq.connections import ArqRedis, RedisSettings  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback when arq wheel is absent in host python

    class Retry(Exception):
        """Fallback compatible con arq.Retry cuando el paquete arq no está instalado."""

        def __init__(self, defer: float | None = None) -> None:
            super().__init__(f"Retry(defer={defer})")
            self.defer = defer
            self.defer_score: int | None = int(defer * 1000) if defer is not None else 0

    class RedisSettings:  # type: ignore[no-redef]
        """Fallback compatible con arq.connections.RedisSettings."""

        def __init__(self, dsn: str = "redis://localhost:6379/0") -> None:
            self.dsn = dsn

        @classmethod
        def from_dsn(cls, dsn: str) -> RedisSettings:
            return cls(dsn=dsn)

    class _ArqJob:
        def __init__(self, job_id: str) -> None:
            self.job_id = job_id

    class ArqRedis:  # type: ignore[no-redef]
        """Pool compatible con ArqRedis respaldado por redis.asyncio."""

        def __init__(self, dsn: str) -> None:
            self._client: aioredis.Redis = aioredis.from_url(dsn, decode_responses=True)

        async def enqueue_job(
            self,
            function: str,
            *args: Any,
            _job_id: str | None = None,
            _job_try: int | None = None,
            **kwargs: Any,
        ) -> _ArqJob:
            actual_id = _job_id or f"job:{uuid.uuid4()}"
            payload = json.dumps(
                {
                    "function": function,
                    "args": args,
                    "job_try": _job_try,
                    "kwargs": kwargs,
                },
                default=str,
            )
            await self._client.set(f"arq:job:{actual_id}", payload, ex=7 * 24 * 3600)
            return _ArqJob(actual_id)

        async def aclose(self) -> None:
            await self._client.aclose()

    async def create_pool(settings_: RedisSettings) -> ArqRedis:
        return ArqRedis(settings_.dsn)

    _arq_mod = types.ModuleType("arq")
    _arq_conn_mod = types.ModuleType("arq.connections")
    _arq_mod.create_pool = create_pool  # type: ignore[attr-defined]
    _arq_mod.Retry = Retry  # type: ignore[attr-defined]
    _arq_conn_mod.ArqRedis = ArqRedis  # type: ignore[attr-defined]
    _arq_conn_mod.RedisSettings = RedisSettings  # type: ignore[attr-defined]
    _arq_mod.connections = _arq_conn_mod  # type: ignore[attr-defined]
    sys.modules.setdefault("arq", _arq_mod)
    sys.modules.setdefault("arq.connections", _arq_conn_mod)

from src.core.config import settings

logger = logging.getLogger(__name__)

STATUS_KEY_PREFIX = "evaluador:eval_status"
LOCK_KEY_PREFIX = "evaluador:eval_lock"
EVENT_CHANNEL_PREFIX = "evaluador:interviews"
DEFAULT_STATUS_TTL_SECONDS = 7 * 24 * 3600  # 7 días de retención


class BrokerConnectionError(Exception):
    """Excepción cuando el broker Redis/ARQ no está disponible o rechaza la conexión."""


class EvaluationQueue:
    """Gestiona el encolado durable de evaluaciones en Redis con ARQ y la persistencia de estados."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._arq_pool: ArqRedis | None = None
        self._redis_client: aioredis.Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _ensure_active_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            self._redis_client = None
            self._arq_pool = None
            self._loop = loop

    async def get_redis_client(self) -> aioredis.Redis:
        """Retorna un cliente redis.asyncio reutilizable vinculado al loop activo."""
        self._ensure_active_loop()
        if self._redis_client is None:
            self._redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis_client

    async def get_arq_pool(self) -> ArqRedis:
        """Retorna un pool de conexiones ARQ vinculado al loop activo."""
        self._ensure_active_loop()
        if self._arq_pool is None:
            redis_settings = RedisSettings.from_dsn(self.redis_url)
            self._arq_pool = await create_pool(redis_settings)
        return self._arq_pool

    async def close(self) -> None:
        """Cierra conexiones activas."""
        if self._arq_pool is not None:
            await self._arq_pool.aclose()
            self._arq_pool = None
        if self._redis_client is not None:
            await self._redis_client.aclose()
            self._redis_client = None
        self._loop = None

    def _status_key(self, interview_id: uuid.UUID) -> str:
        return f"{STATUS_KEY_PREFIX}:{interview_id}"

    def _lock_key(self, interview_id: uuid.UUID) -> str:
        return f"{LOCK_KEY_PREFIX}:{interview_id}"

    def _event_channel(self, interview_id: uuid.UUID) -> str:
        return f"{EVENT_CHANNEL_PREFIX}:{interview_id}:events"

    async def enqueue_evaluation(
        self,
        interview_id: uuid.UUID | str,
        *,
        max_retries: int = 3,
    ) -> str:
        """Encola durablemente la evaluación de una entrevista en Redis usando ARQ.

        Garantiza:
        - Job ID único e idempotente basado en interview_id ('eval:{interview_id}').
        - Registro de estado durable en Redis ('queued').
        - Emisión de evento 'evaluation_queued'.
        - Excepción explícita BrokerConnectionError si Redis no responde.
        """
        int_uuid = interview_id if isinstance(interview_id, uuid.UUID) else uuid.UUID(str(interview_id))
        job_id = f"eval:{int_uuid}"

        try:
            # 1. Registrar estado durable 'queued' en Redis
            await self.set_evaluation_status(
                int_uuid,
                status="queued",
                metadata={"enqueued_at": datetime.now(UTC).isoformat(), "job_id": job_id},
            )

            # 2. Encolar trabajo en ARQ con job_id determinista para idempotencia en cola
            pool = await self.get_arq_pool()
            job = await pool.enqueue_job(
                "evaluate_interview_job",
                str(int_uuid),
                _job_id=job_id,
                _job_try=1,
            )
            actual_job_id = job.job_id if job else job_id
            logger.info("Evaluación encolada exitosamente: interview_id=%s job_id=%s", int_uuid, actual_job_id)
            return actual_job_id
        except (RedisError, OSError) as exc:
            logger.error("Fallo al conectar con el broker Redis al encolar interview_id=%s: %s", int_uuid, exc)
            raise BrokerConnectionError(f"No se pudo encolar la evaluación en Redis: {exc!s}") from exc

    async def set_evaluation_status(
        self,
        interview_id: uuid.UUID | str,
        status: str,
        *,
        metadata: dict[str, Any] | None = None,
        ttl_seconds: int = DEFAULT_STATUS_TTL_SECONDS,
    ) -> None:
        """Persiste el estado de la evaluación en Redis y publica el evento en Pub/Sub."""
        int_uuid = interview_id if isinstance(interview_id, uuid.UUID) else uuid.UUID(str(interview_id))
        client = await self.get_redis_client()

        payload: dict[str, Any] = {
            "interview_id": str(int_uuid),
            "status": status,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if metadata:
            payload.update(metadata)

        payload_json = json.dumps(payload, default=str)
        key = self._status_key(int_uuid)

        try:
            await client.set(key, payload_json, ex=ttl_seconds)
            # Publicar evento en el canal Pub/Sub de la entrevista
            event_msg = json.dumps({"type": f"evaluation_{status}", "payload": payload}, default=str)
            await client.publish(self._event_channel(int_uuid), event_msg)
        except (RedisError, OSError) as exc:
            logger.warning("No se pudo actualizar estado en Redis para interview_id=%s: %s", int_uuid, exc)
            raise BrokerConnectionError(f"Error comunicando con Redis: {exc!s}") from exc

    async def get_evaluation_status(
        self,
        interview_id: uuid.UUID | str,
    ) -> dict[str, Any] | None:
        """Recupera el estado persistido de la evaluación desde Redis."""
        int_uuid = interview_id if isinstance(interview_id, uuid.UUID) else uuid.UUID(str(interview_id))
        client = await self.get_redis_client()
        key = self._status_key(int_uuid)

        try:
            raw = await client.get(key)
            if not raw:
                return None
            return json.loads(raw)
        except (RedisError, OSError) as exc:
            logger.warning("Fallo al leer estado en Redis para interview_id=%s: %s", int_uuid, exc)
            raise BrokerConnectionError(f"Error leyendo de Redis: {exc!s}") from exc

    async def acquire_lock(
        self,
        interview_id: uuid.UUID | str,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Intenta adquirir un lock distribuido exclusivo en Redis para evitar ejecuciones concurrentes."""
        int_uuid = interview_id if isinstance(interview_id, uuid.UUID) else uuid.UUID(str(interview_id))
        client = await self.get_redis_client()
        lock_key = self._lock_key(int_uuid)

        try:
            acquired = await client.set(lock_key, worker_id, nx=True, ex=ttl_seconds)
            return bool(acquired)
        except (RedisError, OSError) as exc:
            logger.warning("Fallo al adquirir lock en Redis para interview_id=%s: %s", int_uuid, exc)
            return False

    async def release_lock(
        self,
        interview_id: uuid.UUID | str,
        worker_id: str,
    ) -> bool:
        """Libera el lock distribuido de la evaluación si pertenece al worker_id."""
        int_uuid = interview_id if isinstance(interview_id, uuid.UUID) else uuid.UUID(str(interview_id))
        client = await self.get_redis_client()
        lock_key = self._lock_key(int_uuid)

        # Script Lua para liberación atómica segura de lock
        lua_release = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            res = await cast("Any", client.eval(lua_release, 1, lock_key, worker_id))
            return bool(res)
        except (RedisError, OSError) as exc:
            logger.warning("Fallo al liberar lock en Redis para interview_id=%s: %s", int_uuid, exc)
            return False


# Singleton global
evaluation_queue = EvaluationQueue()
