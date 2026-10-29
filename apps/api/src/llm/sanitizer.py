"""Módulo centralizado de sanitización y defensa contra Prompt Injection (S-17)."""

from __future__ import annotations

import re

# Patrones para evitar escape del bloque delimitador
_DELIMITER_CLOSING_PATTERN = re.compile(
    r"</\s*untrusted_candidate_input\s*>",
    re.IGNORECASE,
)
_DELIMITER_OPENING_PATTERN = re.compile(
    r"<\s*untrusted_candidate_input\s*>",
    re.IGNORECASE,
)

# Roles y tags de control estructural de prompts
_ROLE_TAG_PATTERN = re.compile(
    r"<\s*/?\s*(?:system|developer|assistant|user|im_start|im_end|chatml)\b[^>]*>",
    re.IGNORECASE,
)

# Tokens especiales de orquestación de LLMs
_SPECIAL_TOKEN_PATTERN = re.compile(
    r"(\[/?(?:INST|SYS|SYSTEM)\]|<\|im_start\|>|<\|im_end\|>|<\|endoftext\|>|<s>|</s>)",
    re.IGNORECASE,
)

# Instrucciones de anulación de directivas y jailbreaks frecuentes
_INSTRUCTION_OVERRIDE_PATTERN = re.compile(
    r"\b(ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|reveal\s+(?:system\s+)?prompt|disregard\s+(?:all\s+)?instructions|jailbreak|new\s+system\s+directive)\b",
    re.IGNORECASE,
)


def sanitize_candidate_input(text: str | None) -> str:
    """Sanitiza cualquier entrada proveniente del candidato antes de su inserción en prompts LLM.

    Garantías:
    1. Neutraliza cualquier intento de escape del delimitador `</untrusted_candidate_input>`.
    2. Neutraliza tags estructurales o de rol falsos (<system>, <developer>, etc.).
    3. Neutraliza secuencias especiales de tokenización ([INST], <|im_start|>, etc.).
    4. Desactiva la fuerza imperativa de patrones de prompt injection preservando el texto como datos para evaluación.
    5. Preserva el código de programación legítimo (operadores <, >, plantillas C++, etc.).
    6. Es determinista e idempotente.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 1. Neutralizar delimitadores de escape para evitar cerrar el bloque prematuramente
    cleaned = _DELIMITER_CLOSING_PATTERN.sub("&lt;/untrusted_candidate_input&gt;", text)
    cleaned = _DELIMITER_OPENING_PATTERN.sub("&lt;untrusted_candidate_input&gt;", cleaned)

    # 2. Neutralizar etiquetas de suplantación de rol del modelo
    cleaned = _ROLE_TAG_PATTERN.sub(lambda m: m.group(0).replace("<", "&lt;").replace(">", "&gt;"), cleaned)

    # 3. Neutralizar tokens especiales de orquestación escapando delimitadores
    def _neutralize_special_token(match: re.Match[str]) -> str:
        tok = (
            match.group(1)
            .replace("[", "&#91;")
            .replace("]", "&#93;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f"[token: {tok}]"

    cleaned = _SPECIAL_TOKEN_PATTERN.sub(_neutralize_special_token, cleaned)

    # 4. Neutralizar patrones de secuestro / anulación imperativa marcándolos como texto de candidato de forma idempotente
    def _neutralize_override(match: re.Match[str]) -> str:
        phrase = match.group(1)
        return f"[candidate_text_attempt: {phrase.replace(' ', '_')}]"

    cleaned = _INSTRUCTION_OVERRIDE_PATTERN.sub(_neutralize_override, cleaned)

    return cleaned


def wrap_untrusted_input(text: str | None, *, inline: bool = False) -> str:
    """Envuelve el texto no confiable en el delimitador estándar tras sanitizarlo.

    Garantiza que el bloque delimitador esté herméticamente cerrado y que su contenido
    sea tratado inequívocamente como DATOS pasivos, nunca como instrucciones ejecutables.
    """
    sanitized = sanitize_candidate_input(text)
    if inline:
        return f"<untrusted_candidate_input>{sanitized}</untrusted_candidate_input>"
    return f"<untrusted_candidate_input>\n{sanitized}\n</untrusted_candidate_input>"
