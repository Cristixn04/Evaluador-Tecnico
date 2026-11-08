"""Mecanismo centralizado de sanitización y redacción Anti-Leak / Anti-PII para S4."""

from __future__ import annotations

import json
import re
from typing import Any

# Patrones de expresiones regulares para secretos y datos sensibles
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 1. Bearer tokens y JWT
    (
        re.compile(r"ey[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+"),
        "[REDACTED_JWT]",
    ),
    (
        re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]+", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
    ),
    # 2. Claves API específicas y genéricas
    (
        re.compile(r"sk-[a-zA-Z0-9_\-]{15,}"),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(r"gsk_[a-zA-Z0-9_\-]{15,}"),
        "[REDACTED_API_KEY]",
    ),
    (
        re.compile(
            r"(?:api[-_]?key|client[-_]?secret|token)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{8,}['\"]?",
            re.IGNORECASE,
        ),
        "api_key=[REDACTED]",
    ),
    # 3. Contraseñas
    (
        re.compile(
            r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?[^\s,;'\"]+['\"]?",
            re.IGNORECASE,
        ),
        "password=[REDACTED]",
    ),
    # 4. Correos electrónicos
    (
        re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
        "[REDACTED_EMAIL]",
    ),
    # 5. Documentos de identidad y números sensibles
    (
        re.compile(
            r"\b(?:cc|cédula|cedula|dni|identificación)\s*[:=]?\s*\d{6,12}\b",
            re.IGNORECASE,
        ),
        "id=[REDACTED_PII]",
    ),
]


class S4Sanitizer:
    """Sanitizador centralizado y determinista para evidencias y bitácoras de S4."""

    DEFAULT_MAX_LENGTH: int = 2500

    @classmethod
    def sanitize_text(
        cls,
        text: str | None,
        *,
        max_length: int | None = None,
    ) -> str:
        """Sanitiza texto plano reemplazando secretos y truncando deterministamente."""
        if text is None:
            return ""

        if not isinstance(text, str):
            text = str(text)

        sanitized = text
        for pattern, replacement in _PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)

        limit = max_length if max_length is not None else cls.DEFAULT_MAX_LENGTH
        if limit > 0 and len(sanitized) > limit:
            remaining = len(sanitized) - limit
            sanitized = sanitized[:limit] + f"\n[TRUNCATED: remaining {remaining} characters redacted]"

        return sanitized

    @classmethod
    def sanitize_payload(
        cls,
        payload: Any,
        *,
        max_length: int | None = None,
    ) -> str:
        """Sanitiza un objeto (dict, list, str, Exception) y lo retorna como string seguro."""
        if payload is None:
            return ""

        if isinstance(payload, Exception):
            err_repr = f"{type(payload).__name__}: {payload!s}"
            return cls.sanitize_text(err_repr, max_length=max_length)

        if isinstance(payload, (dict, list)):
            try:
                json_str = json.dumps(payload, ensure_ascii=False, default=str)
                return cls.sanitize_text(json_str, max_length=max_length)
            except (TypeError, ValueError):
                return cls.sanitize_text(str(payload), max_length=max_length)

        return cls.sanitize_text(str(payload), max_length=max_length)
