"""Pruebas unitarias de costes deterministas y auditabilidad (S-15)."""

import pytest

from src.evaluation.pricing import (
    SUPPORTED_MODEL_RATES,
    calculate_aggregate_evaluation_cost,
    calculate_dual_judge_cost,
    calculate_llm_cost,
    normalize_model_name,
)


def test_pricing_calculation_prompt_and_completion_tokens():
    """1. Cálculo determinista diferenciando tokens de entrada (prompt) y salida (completion)."""
    # grok-4.6: $5.00/1M prompt, $15.00/1M completion
    grok_prompt = 1_000
    grok_comp = 500
    expected_cost = (1_000 * 5.00 + 500 * 15.00) / 1_000_000.0  # 0.005 + 0.0075 = 0.0125
    calculated = calculate_llm_cost("grok-4.6", grok_prompt, grok_comp)
    assert calculated == pytest.approx(expected_cost, abs=1e-6)
    assert calculated == 0.0125

    # Diferenciación estricta: invertir prompt y completion debe dar diferente costo
    inverted = calculate_llm_cost("grok-4.6", grok_comp, grok_prompt)
    assert inverted != calculated
    assert inverted == pytest.approx((500 * 5.00 + 1_000 * 15.00) / 1_000_000.0, abs=1e-6)
    assert inverted == 0.0175

    # gpt-4o-mini: $0.15/1M prompt, $0.60/1M completion
    mini_prompt = 10_000
    mini_comp = 2_000
    expected_mini = (10_000 * 0.15 + 2_000 * 0.60) / 1_000_000.0  # 0.0015 + 0.0012 = 0.0027
    calculated_mini = calculate_llm_cost("gpt-4o-mini", mini_prompt, mini_comp)
    assert calculated_mini == pytest.approx(expected_mini, abs=1e-6)
    assert calculated_mini == 0.0027


def test_pricing_sum_both_judges():
    """2. Suma correcta de costes de ambos jueces en doble evaluación."""
    # Juez 1: grok-4.6, 1200 prompt, 400 completion -> (1200*5 + 400*15)/1e6 = 0.012
    # Juez 2: grok-4.6, 800 prompt, 600 completion -> (800*5 + 600*15)/1e6 = 0.013
    # Prueba directa de la función agregadora de costes
    agg_cost = calculate_aggregate_evaluation_cost(0.012, 0.013, has_second_judge=True)
    assert agg_cost == pytest.approx(0.025, abs=1e-6)

    total_cost = calculate_dual_judge_cost(
        model_1="grok-4.6",
        tokens_prompt_1=1_200,
        tokens_completion_1=400,
        model_2="grok-4.6",
        tokens_prompt_2=800,
        tokens_completion_2=600,
        has_second_judge=True,
    )
    assert total_cost == pytest.approx(0.025, abs=1e-6)

    # Dos jueces con modelos distintos (grok-4.6 y grok-2-mini)
    # Juez 1 (grok-4.6): 1000 prompt, 500 comp -> 0.0125
    # Juez 2 (grok-2-mini): 1000 prompt, 500 comp -> (1000*0.20 + 500*1.00)/1e6 = 0.0007
    mixed_cost = calculate_dual_judge_cost(
        model_1="grok-4.6",
        tokens_prompt_1=1_000,
        tokens_completion_1=500,
        model_2="grok-2-mini",
        tokens_prompt_2=1_000,
        tokens_completion_2=500,
        has_second_judge=True,
    )
    assert mixed_cost == pytest.approx(0.0125 + 0.0007, abs=1e-6)


def test_pricing_unknown_model_or_missing_rate():
    """3. Comportamiento explícito para modelo desconocido o tarifa ausente (retorna None, nunca 0.0)."""
    assert calculate_llm_cost("unknown-model", 1_000, 500) is None
    assert calculate_llm_cost("claude-3-5-sonnet", 1_000, 500) is None
    assert calculate_llm_cost("mock-model", 1_000, 500) is None
    assert calculate_llm_cost("", 1_000, 500) is None
    assert calculate_llm_cost(None, 1_000, 500) is None

    # Si un juez tiene modelo desconocido, el costo total debe ser None (no se inventa costo parcial)
    total_with_unknown = calculate_dual_judge_cost(
        model_1="grok-4.6",
        tokens_prompt_1=1_000,
        tokens_completion_1=500,
        model_2="unregistered-model",
        tokens_prompt_2=1_000,
        tokens_completion_2=500,
        has_second_judge=True,
    )
    assert total_with_unknown is None


def test_pricing_missing_provider_usage_data():
    """4. Ausencia de datos de uso del proveedor (None o inválidos retorna None, nunca 0.0)."""
    assert calculate_llm_cost("grok-4.6", None, 500) is None
    assert calculate_llm_cost("grok-4.6", 1_000, None) is None
    assert calculate_llm_cost("grok-4.6", None, None) is None

    # Tokens negativos o inválidos
    assert calculate_llm_cost("grok-4.6", -10, 500) is None
    assert calculate_llm_cost("grok-4.6", 1_000, -5) is None
    assert calculate_llm_cost("grok-4.6", True, 500) is None
    assert calculate_llm_cost("grok-4.6", "1000", 500) is None

    # Si falta el uso en el segundo juez, el costo total debe ser None
    missing_j2_usage = calculate_dual_judge_cost(
        model_1="grok-4.6",
        tokens_prompt_1=1_000,
        tokens_completion_1=500,
        model_2="grok-4.6",
        tokens_prompt_2=None,
        tokens_completion_2=None,
        has_second_judge=True,
    )
    assert missing_j2_usage is None


def test_pricing_single_judge_fallback():
    """Validar cálculo cuando solo se ejecuta un juez."""
    single_cost = calculate_dual_judge_cost(
        model_1="grok-4.6",
        tokens_prompt_1=1_000,
        tokens_completion_1=500,
        has_second_judge=False,
    )
    assert single_cost == 0.0125


def test_supported_rates_completeness():
    """Validar que todos los modelos configurados y esperados tienen tarifas registradas."""
    expected_models = [
        "grok-4.6",
        "grok-beta",
        "grok-2",
        "grok-2-mini",
        "gpt-4o",
        "gpt-4o-mini",
    ]
    for model in expected_models:
        norm = normalize_model_name(model)
        assert norm in SUPPORTED_MODEL_RATES
        rate = SUPPORTED_MODEL_RATES[norm]
        assert rate.prompt_per_1m > 0
        assert rate.completion_per_1m > 0
