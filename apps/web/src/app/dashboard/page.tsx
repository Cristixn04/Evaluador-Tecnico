"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type Vacancy } from "@/lib/api/client";
import {
  Briefcase,
  Users,
  CheckCircle2,
  PlusCircle,
  ArrowRight,
  TrendingUp,
  FileCheck,
  Sparkles,
} from "lucide-react";

export default function DashboardOverviewPage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [interviews, setInterviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [vacanciesData, interviewsData] = await Promise.all([
          api.getVacancies(),
          api.listOrganizationInterviews("org-colombia-tech").catch(() => []),
        ]);
        setVacancies(vacanciesData);
        setInterviews(interviewsData);
      } catch (err) {
        console.error("Error loading dashboard data", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  return (
    <div className="space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Panel de Control</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Supervisa tus vacantes activas y evaluaciones técnicas objetivas con IA.
          </p>
        </div>
        <Link href="/dashboard/vacancies/new">
          <Button className="gap-2 shadow-sm">
            <PlusCircle className="h-4 w-4" />
            Nueva Vacante con IA
          </Button>
        </Link>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Vacantes Activas
            </CardTitle>
            <Briefcase className="h-4 w-4 text-primary" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{vacancies.length}</div>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <TrendingUp className="h-3 w-3 text-emerald-500" />
              <span>Perfiles sincronizados</span>
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Candidatos Evaluados
            </CardTitle>
            <Users className="h-4 w-4 text-purple-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">8</div>
            <p className="text-xs text-muted-foreground mt-1">Ciego a sesgos demográficos</p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Informes Defendibles
            </CardTitle>
            <FileCheck className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">6</div>
            <p className="text-xs text-muted-foreground mt-1">Con evidencia y doble juez</p>
          </CardContent>
        </Card>

        <Card className="border-border/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Tasa Recomendación
            </CardTitle>
            <CheckCircle2 className="h-4 w-4 text-blue-400" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">75%</div>
            <p className="text-xs text-muted-foreground mt-1">Aprobados para Tech Lead</p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Vacancies Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Vacantes Recientes</h2>
          <Link
            href="/dashboard/vacancies"
            className="text-xs text-primary hover:underline flex items-center gap-1"
          >
            Ver todas <ArrowRight className="h-3 w-3" />
          </Link>
        </div>

        {loading ? (
          <div className="text-sm text-muted-foreground p-8 text-center border rounded-xl border-dashed">
            Cargando vacantes...
          </div>
        ) : vacancies.length === 0 ? (
          <Card className="border-dashed p-8 text-center">
            <Sparkles className="h-8 w-8 text-muted-foreground mx-auto mb-2 opacity-50" />
            <p className="text-sm text-muted-foreground mb-4">
              Aún no tienes vacantes creadas.
            </p>
            <Link href="/dashboard/vacancies/new">
              <Button size="sm">Crear primera vacante</Button>
            </Link>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {vacancies.slice(0, 4).map((vac) => (
              <Card key={vac.id} className="border-border/70 hover:border-border transition-colors">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-base">{vac.title}</CardTitle>
                      <CardDescription className="text-xs capitalize mt-0.5">
                        {vac.role_category} · {vac.seniority}
                      </CardDescription>
                    </div>
                    <Badge variant="outline" className="font-mono text-xs uppercase">
                      {vac.profile?.primary_language || "General"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap gap-1.5">
                    {vac.profile?.required_skills?.slice(0, 4).map((skill) => (
                      <Badge key={skill} variant="secondary" className="text-[11px] font-normal">
                        {skill}
                      </Badge>
                    ))}
                    {(vac.profile?.required_skills?.length || 0) > 4 && (
                      <span className="text-[10px] text-muted-foreground self-center">
                        +{(vac.profile?.required_skills?.length || 0) - 4} más
                      </span>
                    )}
                  </div>

                  <div className="pt-2 border-t border-border/40 flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      Creada: {new Date(vac.created_at).toLocaleDateString("es-CO")}
                    </span>
                    <Link
                      href="/dashboard/vacancies"
                      className="text-primary hover:underline font-medium"
                    >
                      Gestionar candidatos ➡️
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Evaluaciones Recientes e Informes Defendibles */}
      <div className="space-y-4 pt-4 border-t border-border/40">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
              <FileCheck className="h-5 w-5 text-emerald-400" />
              Últimas Evaluaciones e Informes Defendibles
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Candidatos evaluados con rúbrica ciega a PII, radar de competencias y trayectoria forense.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="text-sm text-muted-foreground p-8 text-center border rounded-xl border-dashed">
            Cargando evaluaciones...
          </div>
        ) : interviews.length === 0 ? (
          <Card className="border-dashed p-8 text-center">
            <Users className="h-8 w-8 text-muted-foreground mx-auto mb-2 opacity-50" />
            <p className="text-sm text-muted-foreground">
              Aún no hay entrevistas completadas para mostrar.
            </p>
          </Card>
        ) : (
          <div className="rounded-xl border border-border/70 overflow-hidden bg-card shadow-sm">
            <div className="divide-y divide-border/60">
              {interviews.map((interview) => {
                const isHire = interview.recommendation === "hire";
                const isBorderline = interview.recommendation === "borderline";

                return (
                  <div
                    key={interview.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-muted/40 transition-colors"
                  >
                    <div className="flex items-center gap-3.5">
                      <div className="w-10 h-10 rounded-xl bg-cyan-950/80 border border-cyan-800/80 flex items-center justify-center font-mono font-bold text-xs text-cyan-300">
                        {interview.overall_score ? interview.overall_score.toFixed(1) : "-"}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-semibold text-foreground">
                            {interview.masked_candidate_id}
                          </span>
                          <Badge
                            variant="outline"
                            className={`text-[10px] font-semibold uppercase ${
                              isHire
                                ? "bg-emerald-950/80 text-emerald-300 border-emerald-700/80"
                                : isBorderline
                                ? "bg-amber-950/80 text-amber-300 border-amber-700/80"
                                : "bg-slate-800 text-slate-300 border-slate-700"
                            }`}
                          >
                            {isHire
                              ? "Recomendado"
                              : isBorderline
                              ? "Dudoso"
                              : interview.status === "in_progress"
                              ? "En Progreso"
                              : "No Recomendado"}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {interview.vacancy_title} ·{" "}
                          {new Date(interview.created_at).toLocaleDateString("es-CO")}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-auto">
                      <Link href={`/interview/results/${interview.id}`}>
                        <Button size="sm" variant="outline" className="gap-1.5 text-xs">
                          <span>Ver Informe Defendible</span>
                          <ArrowRight className="h-3.5 w-3.5 text-primary" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
