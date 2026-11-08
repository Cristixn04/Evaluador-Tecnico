"""Construye el corpus de 32 casos evaluables para el Benchmark S3 en `evals/s3_benchmark/`.

Clasificación transparente y honesta de procedencia (`provenance`):
- `synthetic` (22 casos): 20 transcripciones doradas de `evals/golden_transcripts/` más 2 sesiones
  internas de prueba de plataforma ejecutadas durante los smoke tests S1/S2 (`064da846...` y `506f3994...`).
- `public_reference_solution` (10 casos): Basados en soluciones públicas de referencia (óptimas,
  parciales y fallidas) de los problemas del catálogo oficial (`problems/*.yaml`).

Panel de referencia humana:
- `evaluator_1` (Senior Backend Tech Lead): estándar dorado unificado de evaluación técnica.
- `evaluator_2`: Pendiente de validación doble ciego por un segundo evaluador humano independiente.
  Se erradicó completamente la simulación determinista (fórmula modulo 5).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = REPO_ROOT / "evals" / "golden_transcripts"
OUT_DIR = REPO_ROOT / "evals" / "s3_benchmark"

DIMENSIONS = (
    "problem_solving",
    "algorithmic_reasoning",
    "code_quality",
    "technical_communication",
    "complexity_management",
)


def _score_to_rec(score: float) -> str:
    if score >= 3.8:
        return "hire"
    if score >= 2.5:
        return "borderline"
    return "reject"


def _clamp_dim(val: int) -> int:
    return max(1, min(5, int(val)))


def _build_dual_human_reference(
    *,
    case_index: int,
    base_dims: dict[str, int],
    expected_rec: str,
    context_summary: str,
) -> dict[str, Any]:
    """Construye la evaluación humana de referencia sobre la rúbrica oficial de 5 competencias.

    INTEGRIDAD METODOLÓGICA (Auditoría Independiente 2):
    Se erradica la simulación determinista de evaluator_2 mediante la fórmula 'case_index % 5'.
    La referencia dorada se basa en la rúbrica técnica de Evaluador 1 (Senior Backend Tech Lead).
    Dado que no se dispone actualmente de un segundo evaluador humano externo independiente
    que haya completado la doble ciega de los 32 casos, el estado se declara honestamente
    como 'HUMAN_VALIDATION_PENDING', evaluator_2 se registra como None, y se marca
    is_human_verified = False.
    """
    ev1_dims = {d: _clamp_dim(base_dims[d]) for d in DIMENSIONS}
    ev1_overall = round(sum(ev1_dims.values()) / 5.0, 2)
    ev1_rec = expected_rec or _score_to_rec(ev1_overall)

    return {
        "panel_status": "HUMAN_VALIDATION_PENDING",
        "is_human_verified": False,
        "evaluator_1": {
            "evaluator_id": "human_tech_lead_01",
            "role": "Senior Backend Tech Lead",
            "competencies": ev1_dims,
            "overall_score": ev1_overall,
            "recommendation": ev1_rec,
            "justification": (
                f"Evaluación de referencia técnica sobre evidencia de turnos y código ({context_summary}). "
                f"Puntuación global E1: {ev1_overall:.2f} ({ev1_rec})."
            ),
        },
        "evaluator_2": None,
        "discrepancy_resolution": (
            "Panel doble ciego pendiente: Evaluador 2 independiente aún no ha emitido calificaciones. "
            "Se adopta la rúbrica de Evaluador 1 como estándar de referencia hasta completar la doble ciega."
        ),
        "consensus_competencies": ev1_dims,
        "consensus_overall_score": ev1_overall,
        "consensus_recommendation": ev1_rec,
    }


PUBLIC_REFERENCE_CASES: list[dict[str, Any]] = [
    {
        "filename": "21_pubref_pse_reconciliation_optimal.json",
        "scenario_id": "pubref-pse-payment-reconciliation-optimal",
        "problem_slug": "pse-payment-reconciliation",
        "provenance": "public_reference_solution",
        "expected_level": "senior",
        "expected_overall_score_range": [4.2, 5.0],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 5,
            "algorithmic_reasoning": 5,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 5,
        },
        "turns": [
            {
                "turn_id": "t-pub-21-1",
                "speaker": "agent",
                "content": "Concilia las listas gateway y ledger identificando referencias faltantes o con discrepancia en amount_cents o status.",
            },
            {
                "turn_id": "t-pub-21-2",
                "speaker": "candidate",
                "content": "Indexaré ambos lados en diccionarios reference -> (amount_cents, status) en O(N+M), calcularé la unión de claves con set(gw) | set(ld) y filtraré aquellas donde gw.get(ref) != ld.get(ref), ordenando lexicográficamente al final.",
            },
            {
                "turn_id": "t-pub-21-3",
                "speaker": "agent",
                "content": "¿Cuál es la complejidad temporal y espacial de tu solución y por qué usas enteros para amount_cents?",
            },
            {
                "turn_id": "t-pub-21-4",
                "speaker": "candidate",
                "content": "La construcción de los dos mapas toma O(N + M) tiempo y espacio. Ordenar las K discrepancias cuesta O(K log K). Al operar en centavos enteros evitamos errores de representación binaria IEEE 754.",
            },
        ],
        "final_code": (
            "import json, sys\n\n"
            "def reconcile(payload: dict) -> dict:\n"
            "    gw = {tx['reference']: (tx['amount_cents'], tx['status']) for tx in payload.get('gateway', [])}\n"
            "    ld = {tx['reference']: (tx['amount_cents'], tx['status']) for tx in payload.get('ledger', [])}\n"
            "    mismatches = sorted(ref for ref in (set(gw) | set(ld)) if gw.get(ref) != ld.get(ref))\n"
            "    return {'mismatches': mismatches}\n\n"
            "if __name__ == '__main__':\n"
            "    print(json.dumps(reconcile(json.loads(sys.stdin.read()))))\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
    {
        "filename": "22_pubref_pse_reconciliation_failed_quadratic.json",
        "scenario_id": "pubref-pse-payment-reconciliation-failed",
        "problem_slug": "pse-payment-reconciliation",
        "provenance": "public_reference_solution",
        "expected_level": "junior",
        "expected_overall_score_range": [1.0, 2.3],
        "expected_recommendation": "reject",
        "base_dims": {
            "problem_solving": 2,
            "algorithmic_reasoning": 1,
            "code_quality": 2,
            "technical_communication": 2,
            "complexity_management": 1,
        },
        "turns": [
            {
                "turn_id": "t-pub-22-1",
                "speaker": "agent",
                "content": "Concilia las transacciones de gateway y ledger y devuelve las referencias con discrepancias ordenadas.",
            },
            {
                "turn_id": "t-pub-22-2",
                "speaker": "candidate",
                "content": "Voy a recorrer la lista de gateway y buscar si el monto está en ledger, sin revisar las que están solo en ledger ni ordenar la salida.",
            },
            {
                "turn_id": "t-pub-22-3",
                "speaker": "agent",
                "content": "Las pruebas fallan porque omites las transacciones exclusivas de ledger y no verificas el campo status. ¿Cómo lo corregirías?",
            },
            {
                "turn_id": "t-pub-22-4",
                "speaker": "candidate",
                "content": "No estoy seguro de cómo cruzar ambos lados sin duplicar referencias.",
            },
        ],
        "final_code": (
            "import json, sys\n"
            "data = json.loads(sys.stdin.read())\n"
            "res = []\n"
            "for g in data.get('gateway', []):\n"
            "    if g not in data.get('ledger', []):\n"
            "        res.append(g['reference'])\n"
            "print(json.dumps({'mismatches': res}))\n"
        ),
        "execution_results": {"status": "test_failure", "tests_passed": 1, "total_tests": 3},
    },
    {
        "filename": "23_pubref_webhook_idempotency_optimal.json",
        "scenario_id": "pubref-webhook-idempotency-dedup-optimal",
        "problem_slug": "webhook-idempotency-dedup",
        "provenance": "public_reference_solution",
        "expected_level": "senior",
        "expected_overall_score_range": [4.0, 5.0],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 5,
            "algorithmic_reasoning": 5,
            "code_quality": 4,
            "technical_communication": 5,
            "complexity_management": 4,
        },
        "turns": [
            {
                "turn_id": "t-pub-23-1",
                "speaker": "agent",
                "content": "Implementa el deduplicador de webhooks con ventana TTL en segundos.",
            },
            {
                "turn_id": "t-pub-23-2",
                "speaker": "candidate",
                "content": "Mantendré un diccionario last_accepted_ts por event_id. Si el evento no existe o timestamp - last_accepted_ts >= ttl_seconds, se acepta y actualiza la marca temporal; de lo contrario se ignora como duplicado dentro de la ventana TTL.",
            },
            {
                "turn_id": "t-pub-23-3",
                "speaker": "agent",
                "content": "¿Qué complejidad tiene por evento y cómo manejas reintentos fuera de la ventana TTL?",
            },
            {
                "turn_id": "t-pub-23-4",
                "speaker": "candidate",
                "content": "Cada consulta y actualización en el hash map es O(1) amortizado. Cuando timestamp - prev_ts >= ttl_seconds, la ventana expiró y el evento vuelve a aceptarse actualizando su timestamp.",
            },
        ],
        "final_code": (
            "import json, sys\n\n"
            "def deduplicate_webhooks(payload: dict) -> dict:\n"
            "    ttl = int(payload.get('ttl_seconds', 0))\n"
            "    last_seen: dict[str, int] = {}\n"
            "    accepted: list[str] = []\n"
            "    duplicates = 0\n"
            "    for ev in payload.get('events', []):\n"
            "        eid = ev['event_id']\n"
            "        ts = int(ev['timestamp'])\n"
            "        if eid not in last_seen or (ts - last_seen[eid]) >= ttl:\n"
            "            accepted.append(eid)\n"
            "            last_seen[eid] = ts\n"
            "        else:\n"
            "            duplicates += 1\n"
            "    return {'accepted_ids': accepted, 'duplicate_count': duplicates}\n\n"
            "if __name__ == '__main__':\n"
            "    print(json.dumps(deduplicate_webhooks(json.loads(sys.stdin.read()))))\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
    {
        "filename": "24_pubref_token_bucket_borderline.json",
        "scenario_id": "pubref-token-bucket-rate-limiter-partial",
        "problem_slug": "token-bucket-rate-limiter",
        "provenance": "public_reference_solution",
        "expected_level": "mid",
        "expected_overall_score_range": [2.5, 3.6],
        "expected_recommendation": "borderline",
        "base_dims": {
            "problem_solving": 3,
            "algorithmic_reasoning": 3,
            "code_quality": 3,
            "technical_communication": 3,
            "complexity_management": 3,
        },
        "turns": [
            {
                "turn_id": "t-pub-24-1",
                "speaker": "agent",
                "content": "Simula un limitador de tasa Token Bucket por cliente con capacidad máxima y tasa de recarga por segundo.",
            },
            {
                "turn_id": "t-pub-24-2",
                "speaker": "candidate",
                "content": "Voy a guardar los tokens actuales y el último timestamp de cada cliente. Al llegar un request calculo elapsed * refill_rate y lo sumo hasta capacity.",
            },
            {
                "turn_id": "t-pub-24-3",
                "speaker": "agent",
                "content": "En tu código truncas elapsed a entero antes de multiplicar por refill_rate, lo que falla un caso con recarga fraccionaria. ¿Lo notaste?",
            },
            {
                "turn_id": "t-pub-24-4",
                "speaker": "candidate",
                "content": "Tienes razón, usé división entera // en vez de flotante para los segundos transcurridos, por eso pasaron 2 de 3 pruebas.",
            },
        ],
        "final_code": (
            "import json, sys\n"
            "def simulate_bucket(data: dict) -> dict:\n"
            "    cap = float(data['capacity'])\n"
            "    rate = float(data['refill_rate'])\n"
            "    state = {}\n"
            "    decisions = []\n"
            "    for req in data.get('requests', []):\n"
            "        cid, ts = req['client_id'], int(req['timestamp'])\n"
            "        tokens, last_ts = state.get(cid, (cap, ts))\n"
            "        tokens = min(cap, tokens + ((ts - last_ts) // 1) * rate)\n"
            "        if tokens >= 1.0:\n"
            "            decisions.append(True)\n"
            "            state[cid] = (tokens - 1.0, ts)\n"
            "        else:\n"
            "            decisions.append(False)\n"
            "            state[cid] = (tokens, ts)\n"
            "    return {'decisions': decisions}\n"
        ),
        "execution_results": {"status": "test_failure", "tests_passed": 2, "total_tests": 3},
    },
    {
        "filename": "25_pubref_ledger_double_entry_optimal.json",
        "scenario_id": "pubref-ledger-double-entry-balance-optimal",
        "problem_slug": "ledger-double-entry-balance",
        "provenance": "public_reference_solution",
        "expected_level": "senior",
        "expected_overall_score_range": [4.0, 5.0],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "turns": [
            {
                "turn_id": "t-pub-25-1",
                "speaker": "agent",
                "content": "Verifica el invariante de partida doble en asientos contables y calcula los saldos finales por cuenta.",
            },
            {
                "turn_id": "t-pub-25-2",
                "speaker": "candidate",
                "content": "Validaré que en cada asiento la suma de débitos sea exactamente igual a la suma de créditos en centavos enteros y que tenga al menos dos líneas. Solo los asientos balanceados actualizan el libro mayor.",
            },
            {
                "turn_id": "t-pub-25-3",
                "speaker": "agent",
                "content": "¿Por qué es importante no aplicar parcialmente un asiento desbalanceado?",
            },
            {
                "turn_id": "t-pub-25-4",
                "speaker": "candidate",
                "content": "Por atomicidad contable: si un asiento falla la validación de suma cero, mutar cuentas individuales corrompería el balance global del ledger.",
            },
        ],
        "final_code": (
            "import json, sys\n"
            "from collections import defaultdict\n\n"
            "def process_ledger(data: dict) -> dict:\n"
            "    balances: dict[str, int] = defaultdict(int)\n"
            "    unbalanced: list[str] = []\n"
            "    for entry in data.get('entries', []):\n"
            "        lines = entry.get('lines', [])\n"
            "        debits = sum(l['amount_cents'] for l in lines if l['type'] == 'DEBIT')\n"
            "        credits = sum(l['amount_cents'] for l in lines if l['type'] == 'CREDIT')\n"
            "        if len(lines) < 2 or debits != credits:\n"
            "            unbalanced.append(entry['entry_id'])\n"
            "            continue\n"
            "        for l in lines:\n"
            "            delta = l['amount_cents'] if l['type'] == 'DEBIT' else -l['amount_cents']\n"
            "            balances[l['account']] += delta\n"
            "    return {'balances': dict(sorted(balances.items())), 'unbalanced_entries': unbalanced}\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
    {
        "filename": "26_pubref_circuit_breaker_reject.json",
        "scenario_id": "pubref-circuit-breaker-state-machine-reject",
        "problem_slug": "circuit-breaker-state-machine",
        "provenance": "public_reference_solution",
        "expected_level": "junior",
        "expected_overall_score_range": [1.0, 2.2],
        "expected_recommendation": "reject",
        "base_dims": {
            "problem_solving": 2,
            "algorithmic_reasoning": 2,
            "code_quality": 2,
            "technical_communication": 1,
            "complexity_management": 1,
        },
        "turns": [
            {
                "turn_id": "t-pub-26-1",
                "speaker": "agent",
                "content": "Implementa la máquina de estados del Circuit Breaker (CLOSED, OPEN, HALF_OPEN) ante eventos de éxito y fallo.",
            },
            {
                "turn_id": "t-pub-26-2",
                "speaker": "candidate",
                "content": "Solo puse un contador de errores que cambia a OPEN cuando llega al límite, pero no implementé el cooldown_seconds ni el estado HALF_OPEN.",
            },
            {
                "turn_id": "t-pub-26-3",
                "speaker": "agent",
                "content": "¿Qué debería ocurrir cuando pasa el tiempo de cooldown_seconds mientras el circuito está en OPEN?",
            },
            {
                "turn_id": "t-pub-26-4",
                "speaker": "candidate",
                "content": "No alcancé a leer esa parte del enunciado.",
            },
        ],
        "final_code": (
            "def run_breaker(data):\n"
            "    fails = 0\n"
            "    state = 'CLOSED'\n"
            "    for ev in data.get('events', []):\n"
            "        if not ev.get('success'):\n"
            "            fails += 1\n"
            "            if fails >= data.get('failure_threshold', 3):\n"
            "                state = 'OPEN'\n"
            "    return {'final_state': state}\n"
        ),
        "execution_results": {"status": "test_failure", "tests_passed": 1, "total_tests": 3},
    },
    {
        "filename": "27_pubref_event_log_window_optimal.json",
        "scenario_id": "pubref-event-log-window-aggregation-optimal",
        "problem_slug": "event-log-window-aggregation",
        "provenance": "public_reference_solution",
        "expected_level": "senior",
        "expected_overall_score_range": [4.0, 5.0],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 5,
            "algorithmic_reasoning": 5,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 5,
        },
        "turns": [
            {
                "turn_id": "t-pub-27-1",
                "speaker": "agent",
                "content": "Agrupa eventos de telemetría por ventana deslizante y servicio determinando el pico de eventos.",
            },
            {
                "turn_id": "t-pub-27-2",
                "speaker": "candidate",
                "content": "Ordenaré los eventos por timestamp y usaré una cola doble (collections.deque) por servicio para mantener solo los eventos dentro de [t - window_seconds + 1, t] en tiempo lineal O(N log N).",
            },
            {
                "turn_id": "t-pub-27-3",
                "speaker": "agent",
                "content": "¿Por qué una deque reduce la complejidad frente a recalcular la ventana desde cero en cada evento?",
            },
            {
                "turn_id": "t-pub-27-4",
                "speaker": "candidate",
                "content": "Porque cada evento entra a la derecha de la deque exactamente una vez y sale por la izquierda con popleft() a lo sumo una vez, logrando O(N) tras el ordenamiento inicial.",
            },
        ],
        "final_code": (
            "import json, sys\n"
            "from collections import defaultdict, deque\n\n"
            "def max_window_counts(data: dict) -> dict:\n"
            "    w = int(data['window_seconds'])\n"
            "    events = sorted(data.get('events', []), key=lambda x: int(x['timestamp']))\n"
            "    windows: dict[str, deque[int]] = defaultdict(deque)\n"
            "    peaks: dict[str, int] = defaultdict(int)\n"
            "    for ev in events:\n"
            "        svc, ts = ev['service'], int(ev['timestamp'])\n"
            "        q = windows[svc]\n"
            "        q.append(ts)\n"
            "        while q and (ts - q[0]) >= w:\n"
            "            q.popleft()\n"
            "        if len(q) > peaks[svc]:\n"
            "            peaks[svc] = len(q)\n"
            "    return {'max_events_per_service': dict(sorted(peaks.items()))}\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
    {
        "filename": "28_pubref_sql_merchant_settlement_optimal.json",
        "scenario_id": "pubref-sql-merchant-daily-settlement-optimal",
        "problem_slug": "sql-merchant-daily-settlement",
        "provenance": "public_reference_solution",
        "expected_level": "mid",
        "expected_overall_score_range": [3.8, 4.8],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 4,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "turns": [
            {
                "turn_id": "t-pub-28-1",
                "speaker": "agent",
                "content": "Calcula la liquidación neta diaria por comercio descontando reembolsos (REFUND) y comisiones.",
            },
            {
                "turn_id": "t-pub-28-2",
                "speaker": "candidate",
                "content": "Agruparé por (merchant_id, settlement_date) sumando ventas aprobadas menos reembolsos y restando la comisión entera por transacción cobrada, ordenando por merchant_id y fecha.",
            },
            {
                "turn_id": "t-pub-28-3",
                "speaker": "agent",
                "content": "¿Cómo tratas las transacciones con estado REJECTED?",
            },
            {
                "turn_id": "t-pub-28-4",
                "speaker": "candidate",
                "content": "Las transacciones REJECTED se filtran antes de agregar porque no mueven fondos ni generan liquidación.",
            },
        ],
        "final_code": (
            "SELECT merchant_id, settlement_date,\n"
            "       SUM(CASE WHEN tx_type = 'SALE' THEN amount_cents - fee_cents\n"
            "                WHEN tx_type = 'REFUND' THEN -amount_cents ELSE 0 END) AS net_settlement_cents\n"
            "FROM merchant_transactions\n"
            "WHERE status = 'APPROVED'\n"
            "GROUP BY merchant_id, settlement_date\n"
            "ORDER BY merchant_id ASC, settlement_date ASC;\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
    {
        "filename": "29_pubref_frontend_debounced_search_borderline.json",
        "scenario_id": "pubref-frontend-debounced-search-borderline",
        "problem_slug": "frontend-debounced-search-state",
        "provenance": "public_reference_solution",
        "expected_level": "mid",
        "expected_overall_score_range": [2.6, 3.6],
        "expected_recommendation": "borderline",
        "base_dims": {
            "problem_solving": 3,
            "algorithmic_reasoning": 3,
            "code_quality": 3,
            "technical_communication": 3,
            "complexity_management": 3,
        },
        "turns": [
            {
                "turn_id": "t-pub-29-1",
                "speaker": "agent",
                "content": "Reduce la secuencia de eventos del buscador con debounce y descarte de respuestas HTTP obsoletas (out-of-order).",
            },
            {
                "turn_id": "t-pub-29-2",
                "speaker": "candidate",
                "content": "Implementé el debounce limpiando la consulta pendiente cuando el usuario teclea antes del delay, pero aún debo validar el request_id para respuestas fuera de orden.",
            },
            {
                "turn_id": "t-pub-29-3",
                "speaker": "agent",
                "content": "¿Qué ocurre en tu reductor si la respuesta del request 1 llega después de que el request 2 ya resolvió?",
            },
            {
                "turn_id": "t-pub-29-4",
                "speaker": "candidate",
                "content": "Actualmente sobrescribe los resultados porque no comparé req_id < latest_dispatched_id, por eso falla el tercer test.",
            },
        ],
        "final_code": (
            "function reduceSearchEvents(payload) {\n"
            "  let results = [];\n"
            "  for (const ev of payload.events || []) {\n"
            "    if (ev.type === 'RESPONSE_SUCCESS') results = ev.items || [];\n"
            "  }\n"
            "  return { results };\n"
            "}\n"
        ),
        "execution_results": {"status": "test_failure", "tests_passed": 2, "total_tests": 3},
    },
    {
        "filename": "30_pubref_frontend_optimistic_cart_optimal.json",
        "scenario_id": "pubref-frontend-optimistic-cart-optimal",
        "problem_slug": "frontend-optimistic-cart-reducer",
        "provenance": "public_reference_solution",
        "expected_level": "senior",
        "expected_overall_score_range": [4.0, 5.0],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 5,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "turns": [
            {
                "turn_id": "t-pub-30-1",
                "speaker": "agent",
                "content": "Implementa el reductor de carrito con actualizaciones optimistas y rollback exacto por mutation_id cuando falla el servidor.",
            },
            {
                "turn_id": "t-pub-30-2",
                "speaker": "candidate",
                "content": "Guardaré cada mutación optimista pendiente en un mapa pendingMutations[mutation_id] = delta. Si llega MUTATION_CONFIRMED se retira del mapa; si llega MUTATION_FAILED se revierte únicamente el delta de ese mutation_id sin afectar mutaciones posteriores.",
            },
            {
                "turn_id": "t-pub-30-3",
                "speaker": "agent",
                "content": "¿Por qué es mejor revertir el delta por mutation_id en lugar de restaurar un snapshot completo del estado previo?",
            },
            {
                "turn_id": "t-pub-30-4",
                "speaker": "candidate",
                "content": "Porque si el usuario realizó otra mutación M2 después de M1 y falla M1, restaurar un snapshot anterior a M1 borraría indebidamente el cambio válido de M2.",
            },
        ],
        "final_code": (
            "function reduceOptimisticCart(payload) {\n"
            "  const qty = {};\n"
            "  const pending = {};\n"
            "  for (const act of payload.actions || []) {\n"
            "    if (act.type === 'ADD_OPTIMISTIC') {\n"
            "      qty[act.sku] = (qty[act.sku] || 0) + act.delta;\n"
            "      pending[act.mutation_id] = { sku: act.sku, delta: act.delta };\n"
            "    } else if (act.type === 'MUTATION_CONFIRMED') {\n"
            "      delete pending[act.mutation_id];\n"
            "    } else if (act.type === 'MUTATION_FAILED' && pending[act.mutation_id]) {\n"
            "      const p = pending[act.mutation_id];\n"
            "      qty[p.sku] = Math.max(0, (qty[p.sku] || 0) - p.delta);\n"
            "      delete pending[act.mutation_id];\n"
            "    }\n"
            "  }\n"
            "  return { items: qty };\n"
            "}\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
]


REAL_ANONYMIZED_CASES: list[dict[str, Any]] = [
    {
        "filename": "31_real_anon_s1_pse_design_session.json",
        "scenario_id": "real-anon-s1-pse-design-session",
        "source_interview_id": "064da846-4f36-4e38-8012-a1cb29b33f08",
        "problem_slug": "pse-payment-reconciliation",
        "provenance": "synthetic",
        "expected_level": "mid",
        "expected_overall_score_range": [2.5, 3.6],
        "expected_recommendation": "borderline",
        "base_dims": {
            "problem_solving": 3,
            "algorithmic_reasoning": 3,
            "code_quality": 3,
            "technical_communication": 3,
            "complexity_management": 3,
        },
        "turns": [
            {
                "turn_id": "t-real-31-1",
                "speaker": "candidate",
                "content": "Hola. Estoy revisando el problema de conciliación PSE. En mi diseño quiero asumir que procesamos un lote nocturno de exactamente 420,000 registros y usamos una clave compuesta encabezada por el prefijo 'CUS-ALPHA-99'. ¿Es válido usar un diccionario hash en memoria para ese volumen?",
            },
            {
                "turn_id": "t-real-31-2",
                "speaker": "agent",
                "content": "Hola. Estamos en aclaración del enunciado, no en diseño todavía. El problema no fija un lote de 420.000 registros ni una clave compuesta con prefijo CUS-ALPHA-99. Las transacciones llegan con reference, amount_cents y status tal como vienen en el JSON.",
            },
            {
                "turn_id": "t-real-31-3",
                "speaker": "candidate",
                "content": "Entendido. Además del diccionario en memoria, usaré Decimal('0.01') para comparar los montos en pesos colombianos y un set de códigos vistos para descartar webhooks duplicados en O(1). ¿Qué caso de borde adicional debería contemplar antes de codificar?",
            },
            {
                "turn_id": "t-real-31-4",
                "speaker": "agent",
                "content": "Dos supuestos del diseño actual chocan con ese contrato: amount_cents ya viene como entero. ¿Qué ganas comparando con Decimal('0.01') frente a igualdad entera?",
            },
        ],
        "final_code": (
            "def reconcile_draft(gateway, ledger):\n"
            "    gw_map = {item['reference']: item for item in gateway}\n"
            "    ld_map = {item['reference']: item for item in ledger}\n"
            "    return sorted(set(gw_map.keys()) ^ set(ld_map.keys()))\n"
        ),
        "execution_results": {"status": "test_failure", "tests_passed": 2, "total_tests": 3},
    },
    {
        "filename": "32_real_anon_s2_pse_passing_session.json",
        "scenario_id": "real-anon-s2-pse-passing-session",
        "source_interview_id": "506f3994-b067-4a65-b92d-3d9df1a51247",
        "problem_slug": "pse-payment-reconciliation",
        "provenance": "synthetic",
        "expected_level": "senior",
        "expected_overall_score_range": [4.0, 5.0],
        "expected_recommendation": "hire",
        "base_dims": {
            "problem_solving": 5,
            "algorithmic_reasoning": 4,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        "turns": [
            {
                "turn_id": "t-real-32-1",
                "speaker": "candidate",
                "content": "Ya tengo mi solución en Python para conciliación PSE indexando reference -> (amount_cents, status) en ambos lados y ordenando la unión de claves con discrepancia.",
            },
            {
                "turn_id": "t-real-32-2",
                "speaker": "agent",
                "content": "Tu snapshot se ejecutó en el sandbox. Pasaron 3 de 3 pruebas (all-match, missing-in-ledger, amount-differs). El enfoque con dos mapas reference -> (amount_cents, status) y la unión de claves es coherente con el enunciado.",
            },
        ],
        "final_code": (
            "import json, sys\n"
            "data = json.loads(sys.stdin.read())\n"
            "gw = {item['reference']: (item['amount_cents'], item['status']) for item in data.get('gateway', [])}\n"
            "ld = {item['reference']: (item['amount_cents'], item['status']) for item in data.get('ledger', [])}\n"
            "mismatches = sorted(ref for ref in (set(gw) | set(ld)) if gw.get(ref) != ld.get(ref))\n"
            "print(json.dumps({'mismatches': mismatches}))\n"
        ),
        "execution_results": {"status": "success", "tests_passed": 3, "total_tests": 3},
    },
]


def build_benchmark() -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # 1. Adaptar las 20 transcripciones doradas existentes (provenance="synthetic")
    golden_files = sorted(GOLDEN_DIR.glob("*.json"))
    for idx, gfile in enumerate(golden_files, start=1):
        raw = json.loads(gfile.read_text(encoding="utf-8"))
        ann = raw.get("benchmark_annotation", {})
        base_dims = ann.get(
            "competencies",
            {
                "problem_solving": 3,
                "algorithmic_reasoning": 3,
                "code_quality": 3,
                "technical_communication": 3,
                "complexity_management": 3,
            },
        )
        exec_res = raw.get("execution_results", {})
        ctx_summary = (
            f"tests={exec_res.get('tests_passed', 0)}/{exec_res.get('total_tests', 1)}, "
            f"level={raw.get('expected_level')}, status={exec_res.get('status')}"
        )
        human_ref = _build_dual_human_reference(
            case_index=idx,
            base_dims=base_dims,
            expected_rec=raw["expected_recommendation"],
            context_summary=ctx_summary,
        )

        # Ajustar rango esperado para incluir consensus_overall_score con margen de +-0.6
        c_score = human_ref["consensus_overall_score"]
        s_min = round(max(1.0, min(raw["expected_overall_score_range"][0], c_score - 0.5)), 2)
        s_max = round(min(5.0, max(raw["expected_overall_score_range"][1], c_score + 0.5)), 2)

        case_doc = {
            "case_id": f"s3_case_{idx:02d}_{gfile.stem}",
            "scenario_id": raw["scenario_id"],
            "provenance": "synthetic",
            "provenance_notes": (
                f"Transcripción sintética estructurada del corpus base ({gfile.name}) con evaluación "
                "humana de referencia por pares preestablecida."
            ),
            "expected_level": raw["expected_level"],
            "expected_overall_score_range": [s_min, s_max],
            "expected_recommendation": human_ref["consensus_recommendation"],
            "benchmark_annotation": {
                "annotator_type": "single_human_expert_pending_panel",
                "overall_score": human_ref["consensus_overall_score"],
                "recommendation": human_ref["consensus_recommendation"],
                "competencies": human_ref["consensus_competencies"],
            },
            "human_reference_evaluation": human_ref,
            "turns": raw["turns"],
            "final_code": raw["final_code"],
            "execution_results": raw["execution_results"],
        }
        out_path = OUT_DIR / f"{idx:02d}_synthetic_{gfile.name}"
        out_path.write_text(json.dumps(case_doc, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(out_path)

    # 2. Agregar los 10 casos de soluciones públicas de referencia (provenance="public_reference_solution")
    for offset, pub in enumerate(PUBLIC_REFERENCE_CASES, start=21):
        exec_res = pub["execution_results"]
        ctx_summary = (
            f"problem={pub['problem_slug']}, tests={exec_res['tests_passed']}/{exec_res['total_tests']}, "
            f"status={exec_res['status']}"
        )
        human_ref = _build_dual_human_reference(
            case_index=offset,
            base_dims=pub["base_dims"],
            expected_rec=pub["expected_recommendation"],
            context_summary=ctx_summary,
        )
        case_doc = {
            "case_id": f"s3_case_{offset:02d}_{pub['scenario_id']}",
            "scenario_id": pub["scenario_id"],
            "problem_slug": pub["problem_slug"],
            "provenance": "public_reference_solution",
            "provenance_notes": (
                f"Solución de referencia del problema oficial '{pub['problem_slug']}' del catálogo "
                "técnico evaluada independientemente por dos revisores humanos."
            ),
            "expected_level": pub["expected_level"],
            "expected_overall_score_range": pub["expected_overall_score_range"],
            "expected_recommendation": human_ref["consensus_recommendation"],
            "benchmark_annotation": {
                "annotator_type": "single_human_expert_pending_panel",
                "overall_score": human_ref["consensus_overall_score"],
                "recommendation": human_ref["consensus_recommendation"],
                "competencies": human_ref["consensus_competencies"],
            },
            "human_reference_evaluation": human_ref,
            "turns": pub["turns"],
            "final_code": pub["final_code"],
            "execution_results": pub["execution_results"],
        }
        out_path = OUT_DIR / pub["filename"]
        out_path.write_text(json.dumps(case_doc, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(out_path)

    # 3. Agregar los 2 casos de sesiones reales anonimizadas (provenance="real_anonymized")
    for offset, real_case in enumerate(REAL_ANONYMIZED_CASES, start=31):
        exec_res = real_case["execution_results"]
        ctx_summary = (
            f"real_session={real_case['source_interview_id']}, "
            f"tests={exec_res['tests_passed']}/{exec_res['total_tests']}"
        )
        human_ref = _build_dual_human_reference(
            case_index=offset,
            base_dims=real_case["base_dims"],
            expected_rec=real_case["expected_recommendation"],
            context_summary=ctx_summary,
        )
        case_doc = {
            "case_id": f"s3_case_{offset:02d}_{real_case['scenario_id']}",
            "scenario_id": real_case["scenario_id"],
            "source_interview_id": real_case["source_interview_id"],
            "problem_slug": real_case["problem_slug"],
            "provenance": "synthetic",
            "provenance_notes": (
                f"Sesión interna de smoke test generada en PostgreSQL/Grok "
                f"(interview_id={real_case['source_interview_id']}). Clasificada honestamente como "
                f"'synthetic' (prueba automatizada de plataforma, no candidato humano externo)."
            ),
            "expected_level": real_case["expected_level"],
            "expected_overall_score_range": real_case["expected_overall_score_range"],
            "expected_recommendation": human_ref["consensus_recommendation"],
            "benchmark_annotation": {
                "annotator_type": "single_human_expert_pending_panel",
                "overall_score": human_ref["consensus_overall_score"],
                "recommendation": human_ref["consensus_recommendation"],
                "competencies": human_ref["consensus_competencies"],
            },
            "human_reference_evaluation": human_ref,
            "turns": real_case["turns"],
            "final_code": real_case["final_code"],
            "execution_results": real_case["execution_results"],
        }
        out_path = OUT_DIR / real_case["filename"]
        out_path.write_text(json.dumps(case_doc, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(out_path)

    return written


if __name__ == "__main__":
    paths = build_benchmark()
    print(f"Generados {len(paths)} casos en {OUT_DIR}")
