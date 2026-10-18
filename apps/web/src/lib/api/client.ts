import type { paths, components } from "@evaluador/contracts";

export type Vacancy = components["schemas"]["Vacancy"];
export type CreateVacancyRequest = components["schemas"]["CreateVacancyRequest"];
export type InvitationResponse = components["schemas"]["InvitationResponse"];
export type CreateInvitationRequest = components["schemas"]["CreateInvitationRequest"];
export type AnonymousCandidateSession = components["schemas"]["AnonymousCandidateSession"];
export type EvaluationReport = components["schemas"]["EvaluationReport"];
export type InterviewSummary = components["schemas"]["InterviewSummary"];
export type InterviewTrajectory = components["schemas"]["InterviewTrajectory"];
export type TrajectorySnapshot = components["schemas"]["TrajectorySnapshot"];

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

class ApiClient {
  private getHeaders(): HeadersInit {
    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("auth_token");
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }
    }
    return headers;
  }

  // 1. Iniciar sesión
  async login(email: string, password: string) {
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error("Credenciales inválidas");
    const data = await res.json();
    if (typeof window !== "undefined" && data.access_token) {
      localStorage.setItem("auth_token", data.access_token);
    }
    return data;
  }

  // 2. Obtener vacantes
  async getVacancies(): Promise<Vacancy[]> {
    const res = await fetch(`${API_BASE_URL}/vacancies`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error("Error al obtener vacantes");
    return res.json();
  }

  // 3. Crear y analizar vacante con IA
  async createVacancy(data: CreateVacancyRequest): Promise<Vacancy> {
    const res = await fetch(`${API_BASE_URL}/vacancies`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Error al procesar la vacante");
    return res.json();
  }

  // 4. Crear invitación de candidato (PII desacoplada)
  async createInvitation(
    vacancyId: string,
    invitation: CreateInvitationRequest
  ): Promise<InvitationResponse> {
    const res = await fetch(`${API_BASE_URL}/vacancies/${vacancyId}/invitations`, {
      method: "POST",
      headers: this.getHeaders(),
      body: JSON.stringify(invitation),
    });
    if (!res.ok) throw new Error("Error al generar invitación");
    return res.json();
  }

  // 5. Verificar sesión anónima de candidato
  async verifyCandidateSession(token: string): Promise<AnonymousCandidateSession> {
    const res = await fetch(`${API_BASE_URL}/sessions/verify?token=${encodeURIComponent(token)}`, {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
    if (!res.ok) throw new Error("Sesión inválida o expirada");
    return res.json();
  }

  // 6. Obtener evaluación y reporte defendible de una entrevista
  async getEvaluation(interviewId: string): Promise<EvaluationReport> {
    const res = await fetch(`${API_BASE_URL}/interviews/${interviewId}/evaluation`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error("Error al obtener la evaluación de la entrevista");
    return res.json();
  }

  // 7. Obtener la trayectoria cronológica de código para el reproductor
  async getInterviewTrajectory(interviewId: string): Promise<InterviewTrajectory> {
    const res = await fetch(`${API_BASE_URL}/interviews/${interviewId}/trajectory`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error("Error al obtener la trayectoria de la entrevista");
    return res.json();
  }

  // 8. Listar entrevistas de una organización
  async listOrganizationInterviews(organizationId: string): Promise<InterviewSummary[]> {
    const res = await fetch(`${API_BASE_URL}/organizations/${organizationId}/interviews`, {
      headers: this.getHeaders(),
    });
    if (!res.ok) throw new Error("Error al listar las entrevistas");
    return res.json();
  }
}

export const api = new ApiClient();
