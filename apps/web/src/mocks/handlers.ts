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

  // 5. GET /sessions/verify (Candidato entra a la sala - Cero PII)
  http.get("*/sessions/verify", async () => {
    await delay(300);
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
    });
  }),
];
