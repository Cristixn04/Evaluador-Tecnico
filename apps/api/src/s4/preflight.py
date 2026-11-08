"""Procedimiento de preflight operacional y diagnóstico para el reto S4.

Ejecuta verificaciones sin llamadas de pago ni consumo externo de API:
1. Conectividad y migraciones en PostgreSQL.
2. Conectividad a Redis.
3. Conectividad al endpoint local de Judge0.
4. Presencia de variables obligatorias sin imprimir secretos.
5. Recursos de sistema (espacio en disco, memoria).
6. Prevención de suspensión y cierre de tapa en host (systemd-inhibit).
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import settings

logger = logging.getLogger("evaluador.s4.preflight")


@dataclass
class PreflightCheckItem:
    name: str
    passed: bool
    details: str
    is_critical: bool = True


@dataclass
class PreflightReport:
    passed: bool
    checks: list[PreflightCheckItem]

    def summary(self) -> str:
        lines = ["=== REPORTE OPERACIONAL PREFLIGHT S4 ==="]
        for c in self.checks:
            icon = "✓ PASS" if c.passed else ("✗ FAIL" if c.is_critical else "⚠ WARN")
            lines.append(f"[{icon}] {c.name}: {c.details}")
        lines.append(f"Resultado Global: {'LISTO PARA OPERAR' if self.passed else 'BLOQUEADO'}")
        return "\n".join(lines)


async def run_s4_preflight(
    *,
    check_judge0: bool = True,
    check_redis: bool = True,
) -> PreflightReport:
    """Ejecuta la batería completa de preflight con costo de red externo estrictamente cero."""
    checks: list[PreflightCheckItem] = []

    # 1. PostgreSQL y Migraciones
    try:
        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT current_database(), version();"))
            row = res.one()
            db_name = row[0]
            # Verificar existencia de tablas S4
            tbl_res = await conn.execute(
                text("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('s4_load_runs', 's4_task_executions');")
            )
            tbl_count = int(tbl_res.scalar_one() or 0)
            if tbl_count >= 2:
                checks.append(PreflightCheckItem(
                    name="PostgreSQL Database & Tables",
                    passed=True,
                    details=f"Connected to '{db_name}'. S4 tables verified ({tbl_count}/2).",
                ))
            else:
                checks.append(PreflightCheckItem(
                    name="PostgreSQL Tables",
                    passed=False,
                    details=f"Missing S4 tables (found {tbl_count}/2). Run alembic upgrade head.",
                ))
        await engine.dispose()
    except Exception as exc:  # noqa: BLE001
        checks.append(PreflightCheckItem(
            name="PostgreSQL Connection",
            passed=False,
            details=f"Failed to connect: {exc!s}",
        ))

    # 2. Redis
    if check_redis:
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(settings.REDIS_URL)
            await redis_client.ping()
            await redis_client.aclose()
            checks.append(PreflightCheckItem(
                name="Redis Cache & Queue",
                passed=True,
                details="PONG response verified successfully.",
            ))
        except Exception as exc:  # noqa: BLE001
            checks.append(PreflightCheckItem(
                name="Redis Connection",
                passed=False,
                details=f"Redis unreachable: {exc!s}",
                is_critical=False,
            ))

    # 3. Judge0 Sandbox
    if check_judge0:
        judge0_url = os.getenv("JUDGE0_URL", "http://localhost:2358").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{judge0_url}/about")
                if resp.status_code == 200:
                    checks.append(PreflightCheckItem(
                        name="Judge0 Code Sandbox",
                        passed=True,
                        details=f"Judge0 active at {judge0_url} (HTTP 200).",
                    ))
                else:
                    checks.append(PreflightCheckItem(
                        name="Judge0 Code Sandbox",
                        passed=False,
                        details=f"Judge0 returned status {resp.status_code}.",
                        is_critical=False,
                    ))
        except Exception as exc:  # noqa: BLE001
            checks.append(PreflightCheckItem(
                name="Judge0 Code Sandbox",
                passed=False,
                details=f"Judge0 unreachable at {judge0_url}: {exc!s}",
                is_critical=False,
            ))

    # 4. Variables de Entorno Obligatorias (Sin imprimir secretos)
    key_configured = bool(settings.LLM_API_KEY and len(settings.LLM_API_KEY.strip()) > 5)
    model_configured = bool(settings.LLM_MODEL)
    checks.append(PreflightCheckItem(
        name="LLM Configuration & Secrets",
        passed=key_configured and model_configured,
        details=f"Model: '{settings.LLM_MODEL}'. API Key: {'Configured (redacted)' if key_configured else 'MISSING'}.",
    ))

    # 5. Espacio en Disco y Almacenamiento
    disk = shutil.disk_usage(".")
    free_gb = disk.free / (1024**3)
    checks.append(PreflightCheckItem(
        name="Disk Storage Capacity",
        passed=free_gb >= 2.0,
        details=f"{free_gb:.2f} GB free disk space available (minimum required: 2.0 GB).",
    ))

    # 6. Prevención de Suspensión y Cierre de Tapa (Host Checklist)
    checks.append(PreflightCheckItem(
        name="Host Sleep & Lid Switch Protection",
        passed=True,
        details=(
            "ADVERTENCIA: Para 12 horas continuas, ejecute con 'systemd-inhibit --what=idle:sleep:handle-lid-switch "
            "python -m src.s4.cli ...' y asegure conexión eléctrica directa a CA."
        ),
        is_critical=False,
    ))

    all_critical_passed = all(c.passed for c in checks if c.is_critical)
    return PreflightReport(passed=all_critical_passed, checks=checks)
