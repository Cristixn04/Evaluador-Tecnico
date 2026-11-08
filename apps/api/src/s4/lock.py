"""Mecanismo de exclusión mutua entre procesos mediante PostgreSQL Advisory Locks para S4."""

from __future__ import annotations

import hashlib
import logging
import types
import uuid
from typing import Self

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.s4.service import S4Error

logger = logging.getLogger("evaluador.s4.lock")


class S4RunLockAcquisitionError(S4Error):
    """No fue posible adquirir el bloqueo exclusivo de la corrida porque otro proceso la opera."""


def run_id_to_lock_key(run_id: uuid.UUID) -> int:
    """Deriva deterministamente una clave entera con signo de 64 bits para pg_try_advisory_lock."""
    digest = hashlib.sha256(f"s4_load_run_lock:{run_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


class S4RunAdvisoryLock:
    """Gestor de bloqueo consultivo persistente a nivel de sesión PostgreSQL por corrida.
    
    Asegura que únicamente un proceso orquestador active y despache una corrida específica.
    El lock se mantiene activo en su propia conexión dedicada y se libera automáticamente
    al cerrarse la conexión o al invocarse `release()`.
    """

    def __init__(self, engine: AsyncEngine, run_id: uuid.UUID) -> None:
        self.engine = engine
        self.run_id = run_id
        self.lock_key = run_id_to_lock_key(run_id)
        self._connection: AsyncConnection | None = None
        self._is_locked = False

    @property
    def is_locked(self) -> bool:
        """Indica si el lock está actualmente adquirido."""
        return self._is_locked

    async def acquire(self) -> None:
        """Intenta adquirir el advisory lock exclusivo de sesión."""
        if self._is_locked:
            return

        conn = await self.engine.connect()
        try:
            stmt = text("SELECT pg_try_advisory_lock(:key)")
            result = await conn.execute(stmt, {"key": self.lock_key})
            acquired = bool(result.scalar_one())

            if not acquired:
                await conn.close()
                raise S4RunLockAcquisitionError(
                    f"Conflict: Run '{self.run_id}' is already locked by another runner process. "
                    f"Advisory lock key: {self.lock_key}."
                )

            self._connection = conn
            self._is_locked = True
            logger.info(f"Acquired PostgreSQL advisory lock for run '{self.run_id}' (key: {self.lock_key}).")
        except Exception:
            if not self._is_locked:
                await conn.close()
            raise

    async def release(self) -> None:
        """Libera el advisory lock y cierra la conexión dedicada."""
        if not self._is_locked or self._connection is None:
            return

        try:
            stmt = text("SELECT pg_advisory_unlock(:key)")
            await self._connection.execute(stmt, {"key": self.lock_key})
            logger.info(f"Released PostgreSQL advisory lock for run '{self.run_id}' (key: {self.lock_key}).")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Error unlocking advisory lock for run '{self.run_id}': {exc}")
        finally:
            await self._connection.close()
            self._connection = None
            self._is_locked = False

    async def __aenter__(self) -> Self:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        await self.release()
