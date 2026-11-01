"""Cálculo determinista de costes de LLM para auditabilidad (S-15).

Tarifas oficiales documentadas por millón de tokens (USD):
- xAI Grok (https://docs.x.ai/docs/overview#pricing):
  * grok-4.6 (flagship alias en gateway de reto): $5.00 prompt / $15.00 completion
  * grok-beta: $5.00 prompt / $15.00 completion
  * grok-2 / grok-2-1212: $2.00 prompt / $10.00 completion
  * grok-2-vision / grok-2-vision-1212: $2.00 prompt / $10.00 completion
  * grok-2-mini / grok-2-mini-1212: $0.20 prompt / $1.00 completion
- OpenAI (https://openai.com/api/pricing/):
  * gpt-4o / gpt-4o-2024-08-06: $2.50 prompt / $10.00 completion
  * gpt-4o-mini / gpt-4o-mini-2024-07-18: $0.15 prompt / $0.60 completion
  * gpt-4-turbo: $10.00 prompt / $30.00 completion
  * gpt-3.5-turbo: $0.50 prompt / $1.50 completion
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelRate:
    """Tarifas por millón de tokens en USD."""

    prompt_per_1m: float
    completion_per_1m: float


# Tarifas explícitas y documentadas por modelo (USD por 1,000,000 tokens)
SUPPORTED_MODEL_RATES: dict[str, ModelRate] = {
    # Proveedor xAI / proxy reto.pltk.mx
    "grok-4.6": ModelRate(prompt_per_1m=5.00, completion_per_1m=15.00),
    "grok-beta": ModelRate(prompt_per_1m=5.00, completion_per_1m=15.00),
    "grok-2": ModelRate(prompt_per_1m=2.00, completion_per_1m=10.00),
    "grok-2-1212": ModelRate(prompt_per_1m=2.00, completion_per_1m=10.00),
    "grok-2-vision": ModelRate(prompt_per_1m=2.00, completion_per_1m=10.00),
    "grok-2-vision-1212": ModelRate(prompt_per_1m=2.00, completion_per_1m=10.00),
    "grok-2-mini": ModelRate(prompt_per_1m=0.20, completion_per_1m=1.00),
    "grok-2-mini-1212": ModelRate(prompt_per_1m=0.20, completion_per_1m=1.00),
    # Proveedor OpenAI (alternativa compatible)
    "gpt-4o": ModelRate(prompt_per_1m=2.50, completion_per_1m=10.00),
    "gpt-4o-2024-08-06": ModelRate(prompt_per_1m=2.50, completion_per_1m=10.00),
    "gpt-4o-mini": ModelRate(prompt_per_1m=0.15, completion_per_1m=0.60),
    "gpt-4o-mini-2024-07-18": ModelRate(prompt_per_1m=0.15, completion_per_1m=0.60),
    "gpt-4-turbo": ModelRate(prompt_per_1m=10.00, completion_per_1m=30.00),
    "gpt-3.5-turbo": ModelRate(prompt_per_1m=0.50, completion_per_1m=1.50),
}


def normalize_model_name(model_name: str | None) -> str | None:
    """Normaliza el identificador del modelo (minúsculas, sin espacios externos)."""
    if not model_name or not isinstance(model_name, str):
        return None
    cleaned = model_name.strip().lower()
    return cleaned if cleaned else None


def calculate_llm_cost(
    model_name: str | None,
    tokens_prompt: Any,
    tokens_completion: Any,
) -> float | None:
    """Calcula el coste en USD para una llamada LLM de forma determinista.

    Reglas:
    - Retorna None si el modelo es desconocido o no tiene tarifa configurada.
    - Retorna None si tokens_prompt o tokens_completion son None, inválidos o negativos.
    - Nunca retorna 0.0 cuando se desconoce la tarifa o el consumo de tokens.
    """
    normalized_model = normalize_model_name(model_name)
    if not normalized_model:
        return None

    rate = SUPPORTED_MODEL_RATES.get(normalized_model)
    if rate is None:
        logger.debug(
            "Modelo '%s' sin tarifa documentada configurada; coste = None", model_name
        )
        return None

    if tokens_prompt is None or tokens_completion is None:
        return None
    if isinstance(tokens_prompt, bool) or isinstance(tokens_completion, bool):
        return None
    if not isinstance(tokens_prompt, int) or not isinstance(tokens_completion, int):
        return None
    if tokens_prompt < 0 or tokens_completion < 0:
        return None

    cost = (
        tokens_prompt * rate.prompt_per_1m
        + tokens_completion * rate.completion_per_1m
    ) / 1_000_000.0

    return round(cost, 6)


def calculate_aggregate_evaluation_cost(
    judge1_cost: float | None,
    judge2_cost: float | None = None,
    *,
    has_second_judge: bool = True,
) -> float | None:
    """Suma los costes de ambas pasadas de juez.

    Si cualquier pasada que se haya ejecutado no puede ser calculada (None),
    el total se define explícitamente como None para evitar emitir un coste parcial
    que falsee la auditoría de costes.
    """
    if judge1_cost is None:
        return None
    if not has_second_judge:
        return round(judge1_cost, 6)
    if judge2_cost is None:
        return None
    return round(judge1_cost + judge2_cost, 6)


def calculate_dual_judge_cost(
    model_1: str | None,
    tokens_prompt_1: Any,
    tokens_completion_1: Any,
    model_2: str | None = None,
    tokens_prompt_2: Any = None,
    tokens_completion_2: Any = None,
    *,
    has_second_judge: bool = True,
) -> float | None:
    """Calcula deterministamente el coste total sumando ambas pasadas de juez."""
    cost_1 = calculate_llm_cost(model_1, tokens_prompt_1, tokens_completion_1)
    if not has_second_judge:
        return cost_1

    cost_2 = calculate_llm_cost(
        model_2 or model_1, tokens_prompt_2, tokens_completion_2
    )
    return calculate_aggregate_evaluation_cost(
        cost_1, cost_2, has_second_judge=has_second_judge
    )
