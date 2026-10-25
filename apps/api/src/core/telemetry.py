"""Módulo de telemetría estructurada para herramientas del agente (S2).

Proporciona un mecanismo pequeño, seguro y reutilizable para emitir:
- [AGENT_TOOL_CALL:START]
- [AGENT_TOOL_CALL:SUCCESS]
- [AGENT_TOOL_CALL:ERROR]

Reglas estrictas de seguridad (Anti-Leak):
- PROHIBIDO registrar tokens, JWT, contraseñas, API keys.
- PROHIBIDO registrar PII (emails, nombres de candidatos).
- PROHIBIDO registrar código completo, prompts completos o mensajes completos.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

logger = logging.getLogger("agent.telemetry")

_SENSITIVE_PATTERNS = [
    re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"[a-zA-Z0-9_\.\+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-\.]+"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"ey[a-zA-Z0-9_\-]{10,}(\.[a-zA-Z0-9_\-]+)*"),
]


def _sanitize_value(val: Any) -> str:
    """Sanitiza y formatea un valor para el log de telemetría."""
    if val is None:
        return "none"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)

    s = str(val).strip().replace("\n", " ").replace("\r", "").replace("\t", " ")
    for pattern in _SENSITIVE_PATTERNS:
        s = pattern.sub("[REDACTED]", s)

    if '"' in s:
        s = s.replace('"', "'")
    if " " in s:
        if len(s) > 50:
            s = s[:47] + "..."
        return f'"{s}"'
    if len(s) > 50:
        s = s[:47] + "..."
    return s


class ToolCallTelemetry:
    """Rastreador de ciclo de vida de invocación de una herramienta."""

    def __init__(self, tool: str, operation: str) -> None:
        self.tool = tool
        self.operation = operation
        self._start_time: float | None = None
        self._completed = False

    def start(self, **kwargs: Any) -> None:
        """Emite el evento de inicio [AGENT_TOOL_CALL:START]."""
        self._start_time = time.perf_counter()
        params = [f"tool={self.tool}", f"operation={self.operation}"]
        for k, v in kwargs.items():
            params.append(f"{k}={_sanitize_value(v)}")
        msg = f"[AGENT_TOOL_CALL:START] {' '.join(params)}"
        logger.info(msg)

    def success(self, **kwargs: Any) -> None:
        """Emite el evento de éxito [AGENT_TOOL_CALL:SUCCESS].

        Garantiza que no se emita SUCCESS si ya se emitió un estado terminal.
        """
        if self._completed:
            return
        self._completed = True
        duration_ms = self._calc_duration_ms()
        params = [f"tool={self.tool}", f"operation={self.operation}"]
        for k, v in kwargs.items():
            params.append(f"{k}={_sanitize_value(v)}")
        if duration_ms is not None:
            params.append(f"duration_ms={duration_ms}")
        msg = f"[AGENT_TOOL_CALL:SUCCESS] {' '.join(params)}"
        logger.info(msg)

    def error(self, error: Exception | str, **kwargs: Any) -> None:
        """Emite el evento de error [AGENT_TOOL_CALL:ERROR].

        Garantiza que no se emita ERROR si ya se emitió un estado terminal.
        """
        if self._completed:
            return
        self._completed = True
        duration_ms = self._calc_duration_ms()
        err_msg = str(error)
        params = [
            f"tool={self.tool}",
            f"operation={self.operation}",
            f"error={_sanitize_value(err_msg)}",
        ]
        for k, v in kwargs.items():
            params.append(f"{k}={_sanitize_value(v)}")
        if duration_ms is not None:
            params.append(f"duration_ms={duration_ms}")
        msg = f"[AGENT_TOOL_CALL:ERROR] {' '.join(params)}"
        logger.error(msg)

    def _calc_duration_ms(self) -> int | None:
        if self._start_time is None:
            return None
        return max(0, int((time.perf_counter() - self._start_time) * 1000))


def tool_telemetry(tool: str, operation: str) -> ToolCallTelemetry:
    """Factory helper para instanciar el rastreador de telemetría."""
    return ToolCallTelemetry(tool, operation)
