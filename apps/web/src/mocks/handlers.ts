import { http, HttpResponse, delay } from "msw";

export interface MockVacancy {
  id: string;
  title: string;
  role_category: string;
  seniority: "junior" | "mid" | "senior" | "lead";
  profile: {
    required_skills: string[];
    preferred_skills: string[];
    primary_language: string;
    focus_areas: string[];
  };
  created_at: string;
  candidates_count?: number;
}

// Banco inicial de vacantes simuladas
const mockVacancies: MockVacancy[] = [
  {
    id: "vac-001",
    title: "Senior Backend Engineer (Python / FastAPI)",
    role_category: "Backend",
    seniority: "senior",
    profile: {
      required_skills: ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"],
      preferred_skills: ["AWS", "Kafka", "Microservicios"],
      primary_language: "python",
      focus_areas: ["Diseño de APIs", "Concurrencia", "Optimización de consultas SQL"],
    },
    created_at: new Date(Date.now() - 3600000 * 48).toISOString(),
    candidates_count: 5,
  },
  {
    id: "vac-002",
    title: "Frontend Developer (Next.js / TypeScript)",
    role_category: "Frontend",
    seniority: "mid",
    profile: {
      required_skills: ["TypeScript", "React", "Next.js", "Tailwind CSS"],
      preferred_skills: ["Jest / Vitest", "State Management", "WebSockets"],
      primary_language: "javascript",
      focus_areas: ["Componentes accesibles", "Optimización de rendering", "Responsive design"],
    },
    created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
    candidates_count: 3,
  },
];

export const handlers = [
  // 1. POST /auth/login
  http.post("*/auth/login", async ({ request }) => {
    await delay(300);
    const body = (await request.json()) as { email?: string; password?: string };

    if (!body.email) {
      return HttpResponse.json({ message: "Email requerido" }, { status: 400 });
    }

    return HttpResponse.json({
      access_token: "mock-jwt-token-recruiter-xyz",
      token_type: "bearer",
      role: "recruiter",
      organization_id: "org-colombia-tech",
    });
  }),

  // 2. GET /vacancies
  http.get("*/vacancies", async () => {
    await delay(200);
    return HttpResponse.json(mockVacancies);
  }),

  // 3. POST /vacancies (Parser con IA simulado)
  http.post("*/vacancies", async ({ request }) => {
    await delay(1200); // Simula el tiempo de procesamiento del LLM
    const body = (await request.json()) as { title?: string; raw_description?: string };

    const text = (body.raw_description || "").toLowerCase();

    // Detección heurística de lenguaje y seniority para el mock
    let language = "python";
    let role = "Backend";
    let seniority: "junior" | "mid" | "senior" | "lead" = "mid";

    if (text.includes("senior") || text.includes("líder") || text.includes("5+")) {
      seniority = "senior";
    } else if (text.includes("junior") || text.includes("1 año") || text.includes("trainee")) {
      seniority = "junior";
    }

    if (text.includes("react") || text.includes("frontend") || text.includes("next")) {
      role = "Frontend";
      language = "javascript";
    } else if (text.includes("data") || text.includes("sql") || text.includes("analyst")) {
      role = "Data";
      language = "sql";
    }

    const defaultSkills =
      language === "python"
        ? ["Python", "FastAPI", "SQLAlchemy", "PostgreSQL", "Docker"]
        : language === "javascript"
        ? ["TypeScript", "React", "Next.js", "Tailwind CSS", "HTML/CSS"]
        : ["SQL", "PostgreSQL", "ETL", "Python", "Data Modeling"];

    const preferred =
      language === "python"
        ? ["Redis", "AWS", "CI/CD", "AsyncIO"]
        : language === "javascript"
        ? ["State Management", "WebSockets", "Testing Library"]
        : ["BigQuery", "dbt", "Airflow"];

    const newVacancy: MockVacancy = {
      id: `vac-${Date.now().toString(36)}`,
      title: body.title || `${role} Engineer (${language.toUpperCase()})`,
      role_category: role,
      seniority,
      profile: {
        required_skills: defaultSkills,
        preferred_skills: preferred,
        primary_language: language,
        focus_areas: ["Resolución de problemas", "Arquitectura limpia", "Buenas prácticas"],
      },
      created_at: new Date().toISOString(),
      candidates_count: 0,
    };

    mockVacancies.unshift(newVacancy);
    return HttpResponse.json(newVacancy, { status: 201 });
  }),

  // 4. POST /vacancies/:id/invitations (Invitación con PII desacoplada)
  http.post("*/vacancies/:id/invitations", async ({ params, request }) => {
    await delay(400);
    const body = (await request.json()) as { candidate_name?: string; candidate_email?: string };

    const maskedId = `CAND-${Math.random().toString(36).substring(2, 6).toUpperCase()}`;
    const token = `tok_${Math.random().toString(36).substring(2, 10)}`;

    return HttpResponse.json(
      {
        invitation_id: `inv-${Date.now().toString(36)}`,
        masked_candidate_id: maskedId,
        access_url: `${typeof window !== "undefined" ? window.location.origin : "http://localhost:3000"}/interview/live?token=${token}`,
        access_token: token,
        expires_at: new Date(Date.now() + 3600000 * 72).toISOString(),
      },
      { status: 201 }
    );
  }),

  // 5. GET /sessions/verify (Candidato entra a la sala - Cero PII y autenticación de WS)
  http.get("*/sessions/verify", async ({ request }) => {
    await delay(300);
    const url = new URL(request.url);
    const queryToken = url.searchParams.get("token");
    const authHeader = request.headers.get("Authorization");
    const bearerToken = authHeader?.startsWith("Bearer ") ? authHeader.substring(7) : null;
    const token = queryToken || bearerToken;

    if (!token || token === "invalid" || token === "expired") {
      return HttpResponse.json(
        { detail: "Token de invitación inválido o expirado" },
        { status: 401 }
      );
    }

    const shortLivedWsToken = `ws_jwt_${Math.random().toString(36).substring(2, 12)}`;
    const wsUrl = `ws://localhost:8000/api/v1/interviews/sess-live-999/live`;

    return HttpResponse.json({
      session_id: "sess-live-999",
      masked_candidate_id: "CAND-7F2A",
      vacancy_title: "Senior Backend Engineer (Python / FastAPI)",
      current_phase: "INTRO",
      status: "pending",
      problem: {
        id: "prob-pse-conciliacion",
        title: "Conciliación de Pagos PSE y Liquidación Bancaria",
        difficulty: "senior",
        language: "python",
        scenario_preview:
          "Una pasarela de pagos colombiana experimenta discrepancias de redondeo y transacciones huérfanas en conciliaciones de lotes ACH. Diseña el algoritmo de conciliación.",
        tags: ["Fintech", "PSE", "Algoritmos", "Idempotencia"],
      },
      ws_token: shortLivedWsToken,
      ws_url: wsUrl,
    });
  }),

  // 6. GET /interviews/:id/evaluation (Informe defendible y rúbrica ciega a PII)
  http.get("*/interviews/:id/evaluation", async ({ params }) => {
    await delay(350);
    const { id } = params;

    return HttpResponse.json({
      id: (id as string) || "int-001",
      masked_candidate_id: "CAND-7F2A",
      overall_score: 4.2,
      recommendation: "hire",
      needs_human_review: false,
      discrepancy_note: "",
      competencies: {
        "Resolución de Problemas": 4.5,
        "Calidad de Código": 4.0,
        "Diseño y Arquitectura": 4.2,
        "Casos Borde": 3.8,
        "Comunicación Técnica": 4.6,
        "Trayectoria de Depuración": 4.3,
      },
      evidence: [
        {
          competency: "Resolución de Problemas",
          score: 5,
          turn_id: "turn-03",
          evidence_quote:
            "El candidato propuso agrupar las transacciones bancarias en lotes ACH por ventana horaria usando una clave compuesta de idempotencia (id_banco, fecha_valor, referencia_pse).",
          reasoning:
            "Comprensión destacada de sistemas financieros distribuidos y prevención de transacciones duplicadas sin sugerencia previa.",
        },
        {
          competency: "Trayectoria de Depuración",
          score: 4,
          turn_id: "turn-06",
          evidence_quote:
            "Ante el fallo de 'test_conciliacion_con_redondeo' (-$0.02 COP de discrepancia), el candidato identificó la pérdida de precisión en números de punto flotante y refactorizó la lógica usando Decimal y ROUND_HALF_EVEN.",
          reasoning:
            "Excelente rigor de depuración: no aplicó parches superficiales, sino que corrigió la raíz matemática del problema.",
        },
        {
          competency: "Comunicación Técnica",
          score: 5,
          turn_id: "turn-02",
          evidence_quote:
            "¿La pasarela procesa los reversos y contracargos dentro del mismo archivo de compensación o mediante una conciliación asíncrona T+1 separada?",
          reasoning:
            "Formuló preguntas de clarificación profundas sobre las reglas del dominio antes de escribir la primera línea de código.",
        },
        {
          competency: "Casos Borde",
          score: 4,
          turn_id: "turn-07",
          evidence_quote:
            "Implementó validación estricta para registros con estado 'EN_PROCESO' ignorándolos de la sumatoria de liquidación final pero marcándolos en el reporte de auditoría.",
          reasoning:
            "Consideró transacciones en vuelo sin que fuera necesario indicárselo explícitamente en el enunciado.",
        },
        {
          competency: "Diseño y Arquitectura",
          score: 4,
          turn_id: "turn-04",
          evidence_quote:
            "Separó claramente la capa de ingestión y normalización de registros de la lógica de balanceo contable mediante un generador de iteración en memoria.",
          reasoning:
            "Diseño modular con bajo acoplamiento y control eficiente de memoria para volúmenes medianos a altos.",
        },
      ],
      strengths: [
        "Uso impecable de tipos de datos de alta precisión financiera (Decimal) en Python.",
        "Proactividad sobresaliente en la fase de clarificación con preguntas de negocio pertinentes.",
        "Trayectoria de depuración metódica: analizó el traceback de Judge0 y resolvió la discrepancia en menos de 3 minutos.",
      ],
      risks: [
        "La primera versión del algoritmo utilizaba un bucle anidado O(N*M); requirió una sugerencia leve del evaluador para usar un diccionario indexado O(N+M).",
      ],
      suggested_human_questions: [
        "¿Cómo escalarías este servicio de conciliación si el volumen de transacciones de PSE aumentara a 5.000.000 por hora durante un día de Cyberlunes?",
        "Si la red ACH reporta una caída durante el envío del archivo de compensación, ¿qué mecanismo de recuperación e idempotencia aplicarías?",
      ],
    });
  }),

  // 7. GET /interviews/:id/trajectory (Trayectoria cronológica para el Timeline Player)
  http.get("*/interviews/:id/trajectory", async ({ params }) => {
    await delay(300);
    const { id } = params;

    return HttpResponse.json({
      interview_id: (id as string) || "int-001",
      total_duration_seconds: 2100, // 35 minutos
      snapshots: [
        {
          timestamp_offset_seconds: 180, // Minuto 3
          phase: "PROBLEM",
          reason: "phase_transition",
          code: `# Conciliación de Pagos PSE - Enunciado inicial
# Leyendo requisitos y restricciones del sistema...
`,
          language: "python",
          tests_passed: 0,
          total_tests: 4,
          execution_status: "test_failure",
          event_note: "El candidato inicia la lectura del problema y plantea preguntas iniciales.",
        },
        {
          timestamp_offset_seconds: 480, // Minuto 8
          phase: "DESIGN",
          reason: "phase_transition",
          code: `# Diseño de arquitectura:
# 1. Parsear archivo ACH de banco
# 2. Indexar transacciones internas por (referencia, fecha)
# 3. Conciliar diferencias con tolerancia estricta
# 4. Generar reporte de discrepancias

def conciliar_lote_pse(transacciones_internas, archivo_ach):
    pass
`,
          language: "python",
          tests_passed: 0,
          total_tests: 4,
          execution_status: "test_failure",
          event_note: "Estructura el boceto inicial y valida supuestos en el chat.",
        },
        {
          timestamp_offset_seconds: 960, // Minuto 16
          phase: "CODING",
          reason: "run",
          code: `def conciliar_lote_pse(transacciones_internas, archivo_ach):
    conciliadas = []
    discrepancias = []
    
    # Búsqueda inicial O(N*M)
    for ext in archivo_ach:
        encontrada = False
        for interna in transacciones_internas:
            if interna["ref"] == ext["referencia"]:
                diff = float(interna["monto"]) - float(ext["valor"])
                if diff == 0.0:
                    conciliadas.append(interna["id"])
                else:
                    discrepancias.append((interna["id"], diff))
                encontrada = True
                break
        if not encontrada:
            discrepancias.append((ext["referencia"], "HUERFANA"))
            
    return {"conciliadas": conciliadas, "discrepancias": discrepancias}
`,
          language: "python",
          tests_passed: 1,
          total_tests: 4,
          execution_status: "test_failure",
          event_note: "Primera ejecución de pruebas en Judge0: fallan 3 de 4 pruebas por precisión float y rendimiento.",
        },
        {
          timestamp_offset_seconds: 1350, // Minuto 22.5
          phase: "CODING",
          reason: "debounce",
          code: `from decimal import Decimal, ROUND_HALF_EVEN

def conciliar_lote_pse(transacciones_internas, archivo_ach):
    # Optimización a O(N+M) usando hash map indexado
    indice_internas = {
        item["ref"]: item for item in transacciones_internas
    }
    
    conciliadas = []
    discrepancias = []
    
    for ext in archivo_ach:
        ref = ext.get("referencia")
        if ref in indice_internas:
            interna = indice_internas[ref]
            monto_int = Decimal(str(interna["monto"]))
            monto_ext = Decimal(str(ext["valor"]))
            diff = (monto_int - monto_ext).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            
            if diff == Decimal("0.00"):
                conciliadas.append(interna["id"])
            else:
                discrepancias.append({"id": interna["id"], "diferencia": str(diff)})
        else:
            discrepancias.append({"referencia": ref, "estado": "HUERFANA"})
            
    return {"conciliadas": conciliadas, "discrepancias": discrepancias}
`,
          language: "python",
          tests_passed: 3,
          total_tests: 4,
          execution_status: "test_failure",
          event_note: "Refactorización matemática con Decimal e indexación hash. Solo falta caso borde de estados PENDIENTE.",
        },
        {
          timestamp_offset_seconds: 1720, // Minuto 28.6
          phase: "CODING",
          reason: "run",
          code: `from decimal import Decimal, ROUND_HALF_EVEN
from typing import List, Dict, Any

def conciliar_lote_pse(
    transacciones_internas: List[Dict[str, Any]], 
    archivo_ach: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Concilia lotes de transacciones ACH frente al registro interno de PSE.
    Idempotente, tolerante a fallos de redondeo monetario y eficiente O(N+M).
    """
    # Excluir transacciones en estado de tránsito antes de liquidar
    indice_internas = {
        item["ref"]: item 
        for item in transacciones_internas 
        if item.get("estado") != "PENDIENTE"
    }
    
    conciliadas: List[str] = []
    discrepancias: List[Dict[str, Any]] = []
    
    for ext in archivo_ach:
        ref = ext.get("referencia")
        if ref in indice_internas:
            interna = indice_internas[ref]
            monto_int = Decimal(str(interna["monto"]))
            monto_ext = Decimal(str(ext["valor"]))
            diff = (monto_int - monto_ext).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            
            if diff == Decimal("0.00"):
                conciliadas.append(interna["id"])
            else:
                discrepancias.append({
                    "id": interna["id"], 
                    "diferencia": str(diff),
                    "motivo": "DISCREPANCIA_REDONDEO"
                })
        else:
            discrepancias.append({
                "referencia": ref, 
                "estado": "HUERFANA"
            })
            
    return {
        "conciliadas": conciliadas, 
        "discrepancias": discrepancias,
        "total_procesadas": len(archivo_ach)
    }
`,
          language: "python",
          tests_passed: 4,
          total_tests: 4,
          execution_status: "success",
          event_note: "¡Suite completa en verde! 4/4 pruebas unitarias aprobadas en 42ms.",
        },
        {
          timestamp_offset_seconds: 2050, // Minuto 34.1
          phase: "PROBE",
          reason: "phase_transition",
          code: `from decimal import Decimal, ROUND_HALF_EVEN
from typing import List, Dict, Any

def conciliar_lote_pse(
    transacciones_internas: List[Dict[str, Any]], 
    archivo_ach: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Conciliación bancaria ACH / PSE optimizada y defendible.
    Cumple normatividad de precisión bancaria colombiana.
    """
    indice_internas = {
        item["ref"]: item 
        for item in transacciones_internas 
        if item.get("estado") != "PENDIENTE"
    }
    
    conciliadas: List[str] = []
    discrepancias: List[Dict[str, Any]] = []
    
    for ext in archivo_ach:
        ref = ext.get("referencia")
        if ref in indice_internas:
            interna = indice_internas[ref]
            monto_int = Decimal(str(interna["monto"]))
            monto_ext = Decimal(str(ext["valor"]))
            diff = (monto_int - monto_ext).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            
            if diff == Decimal("0.00"):
                conciliadas.append(interna["id"])
            else:
                discrepancias.append({
                    "id": interna["id"], 
                    "diferencia": str(diff),
                    "motivo": "DISCREPANCIA_REDONDEO"
                })
        else:
            discrepancias.append({
                "referencia": ref, 
                "estado": "HUERFANA"
            })
            
    return {
        "conciliadas": conciliadas, 
        "discrepancias": discrepancias,
        "total_procesadas": len(archivo_ach)
    }
`,
          language: "python",
          tests_passed: 4,
          total_tests: 4,
          execution_status: "success",
          event_note: "Fase PROBE superada: El candidato justificó la complejidad temporal O(N+M) y la elección de ROUND_HALF_EVEN.",
        },
      ],
    });
  }),

  // 8. GET /organizations/:id/interviews (Lista de entrevistas para el reclutador)
  http.get("*/organizations/:id/interviews", async () => {
    await delay(200);
    return HttpResponse.json([
      {
        id: "int-001",
        masked_candidate_id: "CAND-7F2A",
        vacancy_title: "Senior Backend Engineer (Python / FastAPI)",
        status: "evaluated",
        overall_score: 4.2,
        recommendation: "hire",
        created_at: new Date(Date.now() - 3600000 * 2).toISOString(),
      },
      {
        id: "int-002",
        masked_candidate_id: "CAND-3B91",
        vacancy_title: "Senior Backend Engineer (Python / FastAPI)",
        status: "evaluated",
        overall_score: 2.8,
        recommendation: "borderline",
        created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
      },
      {
        id: "int-003",
        masked_candidate_id: "CAND-9K42",
        vacancy_title: "Frontend Developer (Next.js / TypeScript)",
        status: "evaluated",
        overall_score: 4.6,
        recommendation: "hire",
        created_at: new Date(Date.now() - 3600000 * 72).toISOString(),
      },
      {
        id: "int-004",
        masked_candidate_id: "CAND-1D88",
        vacancy_title: "Senior Backend Engineer (Python / FastAPI)",
        status: "in_progress",
        overall_score: 0,
        recommendation: "pending",
        created_at: new Date(Date.now() - 3600000 * 1).toISOString(),
      },
    ]);
  }),
];
