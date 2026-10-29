"""Pruebas unitarias para el Harness de Calibración Estadística (S-21).

Verifica el rigor metodológico del cálculo de Spearman y Kappa de Cohen ponderado,
resolución de empates, gestión explícita de casos límite (varianza nula, división por cero),
e integridad del corpus de 20 transcripciones doradas.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.calibrate import (
    fractional_ranks,
    run_calibration,
    spearman_correlation,
    validate_transcript_schema,
    weighted_cohen_kappa,
)


def test_fractional_ranks_handling_ties() -> None:
    # Sin empates
    assert fractional_ranks([10.0, 20.0, 30.0]) == [1.0, 2.0, 3.0]
    assert fractional_ranks([30.0, 10.0, 20.0]) == [3.0, 1.0, 2.0]

    # Con empates: [1.0, 3.0, 3.0, 4.0] -> 3.0 comparte posiciones 2 y 3 -> (2+3)/2 = 2.5
    ranks = fractional_ranks([3.0, 1.0, 3.0, 4.0])
    assert ranks == [2.5, 1.0, 2.5, 4.0]

    # Todos empatados
    ranks_all_tied = fractional_ranks([5.0, 5.0, 5.0])
    assert ranks_all_tied == [2.0, 2.0, 2.0]


def test_spearman_correlation_exact_and_monotonic() -> None:
    # Perfectamente monotónica creciente -> r_s = 1.0
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 20.0, 30.0, 40.0, 50.0]
    r = spearman_correlation(x, y)
    assert r is not None
    assert math.isclose(r, 1.0, abs_tol=1e-4)

    # Perfectamente monotónica decreciente -> r_s = -1.0
    y_rev = [50.0, 40.0, 30.0, 20.0, 10.0]
    r_neg = spearman_correlation(x, y_rev)
    assert r_neg is not None
    assert math.isclose(r_neg, -1.0, abs_tol=1e-4)

    # Con empates en ambas listas
    x_ties = [1.0, 2.0, 2.0, 4.0]
    y_ties = [10.0, 20.0, 20.0, 40.0]
    r_ties = spearman_correlation(x_ties, y_ties)
    assert r_ties is not None
    assert math.isclose(r_ties, 1.0, abs_tol=1e-4)


def test_spearman_correlation_zero_variance_and_undefined() -> None:
    # Varianza nula en x: correlación matemáticamente no definida
    x_flat = [3.0, 3.0, 3.0, 3.0]
    y = [1.0, 2.0, 3.0, 4.0]
    assert spearman_correlation(x_flat, y) is None

    # Varianza nula en y
    assert spearman_correlation(y, x_flat) is None

    # Muestras insuficientes o desiguales
    assert spearman_correlation([1.0], [1.0]) is None
    assert spearman_correlation([1.0, 2.0], [1.0]) is None


def test_weighted_cohen_kappa_computation() -> None:
    # Acuerdo perfecto (diagonal completa) -> kappa = 1.0
    actual = [0, 1, 2, 0, 1, 2]
    pred = [0, 1, 2, 0, 1, 2]
    k_perf = weighted_cohen_kappa(actual, pred, num_categories=3, weights="quadratic")
    assert k_perf is not None
    assert math.isclose(k_perf, 1.0, abs_tol=1e-4)

    # Desacuerdo moderado vs desacuerdo extremo
    # Desacuerdo adyacente (0 vs 1) penaliza menos que (0 vs 2) en cuadrático
    actual_adj = [0, 1, 2]
    pred_adj = [1, 2, 1]
    k_adj = weighted_cohen_kappa(actual_adj, pred_adj, num_categories=3, weights="quadratic")
    assert k_adj is not None
    assert -1.0 <= k_adj <= 1.0


def test_weighted_cohen_kappa_zero_variance_undefined() -> None:
    # Todos en la misma clase: expected disagreement es 0.0 -> kappa indefinido
    actual_same = [1, 1, 1, 1]
    pred_same = [1, 1, 1, 1]
    assert weighted_cohen_kappa(actual_same, pred_same, num_categories=3) is None

    # Datos inválidos
    assert weighted_cohen_kappa([0, 1], [0], num_categories=3) is None
    assert weighted_cohen_kappa([], [], num_categories=3) is None


def test_corpus_size_and_schema_validation() -> None:
    transcripts_dir = REPO_ROOT / "evals" / "golden_transcripts"
    assert transcripts_dir.exists(), f"Directorio no encontrado: {transcripts_dir}"

    files = list(transcripts_dir.glob("*.json"))
    assert len(files) == 20, f"Se requieren exactamente 20 transcripciones doradas, encontradas: {len(files)}"

    for fpath in files:
        import json

        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        validate_transcript_schema(data, fpath)


def test_full_calibration_harness_execution() -> None:
    transcripts_dir = REPO_ROOT / "evals" / "golden_transcripts"
    results = run_calibration(transcripts_dir=transcripts_dir, live_llm=False, quiet=True)

    assert results["total_transcripts"] == 20
    assert results["in_range_rate_pct"] >= 80.0
    assert results["spearman_correlation"] is not None
    assert results["spearman_correlation"] >= 0.70
    assert results["quadratic_weighted_cohen_kappa"] is not None
    assert results["quadratic_weighted_cohen_kappa"] >= 0.60
    assert results["calibration_passed"] is True
    # Transparencia de anotaciones: no afirmar erróneamente que son humanas
    assert results["annotator_distribution"]["synthetic_benchmark"] == 20
    assert results["is_human_verified"] is False
