"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  Search,
  SlidersHorizontal,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  X,
  RotateCcw,
} from "lucide-react";

export default function DashboardOverviewPage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [interviews, setInterviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Estados de ordenamiento y filtrado avanzado (C-12)
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRecommendation, setSelectedRecommendation] = useState<string>("all");
  const [minScore, setMinScore] = useState<number>(0);
  const [sortColumn, setSortColumn] = useState<"score" | "date" | "candidate">("date");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");

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

  const handleSort = (col: "score" | "date" | "candidate") => {
    if (sortColumn === col) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortColumn(col);
      setSortDirection(col === "score" ? "desc" : "asc");
    }
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setSelectedRecommendation("all");
    setMinScore(0);
    setSortColumn("date");
    setSortDirection("desc");
  };

  const hasActiveFilters = searchQuery !== "" || selectedRecommendation !== "all" || minScore > 0;

  const filteredInterviews = useMemo(() => {
    return interviews
      .filter((int) => {
        // Búsqueda por texto (candidato o título de vacante)
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchesCand = int.masked_candidate_id?.toLowerCase().includes(q);
          const matchesVac = int.vacancy_title?.toLowerCase().includes(q);
          if (!matchesCand && !matchesVac) return false;
        }

        // Filtro por recomendación
        if (selectedRecommendation !== "all") {
          if (selectedRecommendation === "in_progress") {
            if (int.status !== "in_progress") return false;
          } else if (int.recommendation !== selectedRecommendation) {
            return false;
          }
        }

        // Filtro por score mínimo
        if (minScore > 0) {
          if (!int.overall_score || int.overall_score < minScore) return false;
        }

        return true;
      })
      .sort((a, b) => {
        let comparison = 0;
        if (sortColumn === "score") {
          const scoreA = typeof a.overall_score === "number" ? a.overall_score : 0;
          const scoreB = typeof b.overall_score === "number" ? b.overall_score : 0;
          comparison = scoreA - scoreB;
        } else if (sortColumn === "date") {
          const dateA = new Date(a.created_at).getTime() || 0;
          const dateB = new Date(b.created_at).getTime() || 0;
          comparison = dateA - dateB;
        } else if (sortColumn === "candidate") {
          const candA = a.masked_candidate_id || "";
          const candB = b.masked_candidate_id || "";
          comparison = candA.localeCompare(candB);
        }
        return sortDirection === "asc" ? comparison : -comparison;
      });
  }, [interviews, searchQuery, selectedRecommendation, minScore, sortColumn, sortDirection]);

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
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2">
              <FileCheck className="h-5 w-5 text-emerald-400" />
              Últimas Evaluaciones e Informes Defendibles
            </h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Candidatos evaluados con rúbrica ciega a PII, radar de competencias y trayectoria forense.
            </p>
          </div>

          {/* Contador de resultados */}
          {!loading && interviews.length > 0 && (
            <div className="text-xs text-muted-foreground font-mono">
              Mostrando {filteredInterviews.length} de {interviews.length} evaluaciones
            </div>
          )}
        </div>

        {/* Barra de Filtros y Búsqueda (C-12) */}
        {!loading && interviews.length > 0 && (
          <div className="flex flex-wrap items-center gap-3 p-3 rounded-xl bg-card border border-border/70 shadow-sm text-xs">
            {/* Input de Búsqueda */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Buscar por ID de candidato o título de vacante..."
                aria-label="Buscar por ID de candidato o vacante"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-8 pl-8 text-xs bg-background focus-visible:ring-1"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  aria-label="Limpiar búsqueda"
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {/* Filtro por Recomendación */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="filterRec" className="text-muted-foreground whitespace-nowrap">
                Recomendación:
              </label>
              <select
                id="filterRec"
                aria-label="Filtrar por recomendación"
                value={selectedRecommendation}
                onChange={(e) => setSelectedRecommendation(e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value="all">Todas</option>
                <option value="hire">Recomendado (Hire)</option>
                <option value="borderline">Dudoso (Borderline)</option>
                <option value="reject">No Recomendado (Reject)</option>
                <option value="in_progress">En Progreso</option>
              </select>
            </div>

            {/* Filtro por Score Mínimo */}
            <div className="flex items-center gap-1.5">
              <label htmlFor="filterScore" className="text-muted-foreground whitespace-nowrap">
                Puntaje Mínimo:
              </label>
              <select
                id="filterScore"
                aria-label="Filtrar por puntaje mínimo"
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="h-8 rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                <option value={0}>Todos los puntajes</option>
                <option value={4.0}>≥ 4.0 (Sobresaliente)</option>
                <option value={3.5}>≥ 3.5 (Bueno)</option>
                <option value={3.0}>≥ 3.0 (Aceptable)</option>
              </select>
            </div>

            {/* Botón Restablecer */}
            {hasActiveFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetFilters}
                className="h-8 text-xs gap-1 text-muted-foreground hover:text-foreground"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Restablecer</span>
              </Button>
            )}
          </div>
        )}

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
        ) : filteredInterviews.length === 0 ? (
          <Card className="border-dashed p-8 text-center space-y-3">
            <SlidersHorizontal className="h-8 w-8 text-muted-foreground mx-auto opacity-50" />
            <p className="text-sm text-muted-foreground">
              No se encontraron evaluaciones con los filtros aplicados.
            </p>
            <Button size="sm" variant="outline" onClick={handleResetFilters} className="text-xs gap-1.5">
              <RotateCcw className="h-3 w-3" />
              <span>Limpiar filtros de búsqueda</span>
            </Button>
          </Card>
        ) : (
          <div className="rounded-xl border border-border/70 overflow-hidden bg-card shadow-sm">
            {/* Cabecera con Columnas Ordenables */}
            <div className="bg-muted/40 border-b border-border/60 px-4 py-2.5 flex items-center justify-between text-xs font-semibold text-muted-foreground">
              <div className="flex items-center gap-6">
                <button
                  type="button"
                  onClick={() => handleSort("score")}
                  aria-label={`Ordenar por puntaje: orden actual ${sortColumn === "score" ? (sortDirection === "asc" ? "ascendente" : "descendente") : "ninguno"}`}
                  className="flex items-center gap-1.5 hover:text-foreground transition-colors cursor-pointer select-none"
                >
                  <span>Score</span>
                  {sortColumn === "score" ? (
                    sortDirection === "asc" ? (
                      <ArrowUp className="h-3 w-3 text-primary" />
                    ) : (
                      <ArrowDown className="h-3 w-3 text-primary" />
                    )
                  ) : (
                    <ArrowUpDown className="h-3 w-3 opacity-40" />
                  )}
                </button>

                <button
                  type="button"
                  onClick={() => handleSort("candidate")}
                  aria-label={`Ordenar por candidato: orden actual ${sortColumn === "candidate" ? (sortDirection === "asc" ? "ascendente" : "descendente") : "ninguno"}`}
                  className="flex items-center gap-1.5 hover:text-foreground transition-colors cursor-pointer select-none"
                >
                  <span>Candidato & Vacante</span>
                  {sortColumn === "candidate" ? (
                    sortDirection === "asc" ? (
                      <ArrowUp className="h-3 w-3 text-primary" />
                    ) : (
                      <ArrowDown className="h-3 w-3 text-primary" />
                    )
                  ) : (
                    <ArrowUpDown className="h-3 w-3 opacity-40" />
                  )}
                </button>
              </div>

              <div className="flex items-center gap-4">
                <button
                  type="button"
                  onClick={() => handleSort("date")}
                  aria-label={`Ordenar por fecha: orden actual ${sortColumn === "date" ? (sortDirection === "asc" ? "ascendente" : "descendente") : "ninguno"}`}
                  className="flex items-center gap-1.5 hover:text-foreground transition-colors cursor-pointer select-none"
                >
                  <span>Fecha</span>
                  {sortColumn === "date" ? (
                    sortDirection === "asc" ? (
                      <ArrowUp className="h-3 w-3 text-primary" />
                    ) : (
                      <ArrowDown className="h-3 w-3 text-primary" />
                    )
                  ) : (
                    <ArrowUpDown className="h-3 w-3 opacity-40" />
                  )}
                </button>
                <span className="hidden sm:inline">Acciones</span>
              </div>
            </div>

            {/* Filas de Evaluaciones */}
            <div className="divide-y divide-border/60">
              {filteredInterviews.map((interview) => {
                const isHire = interview.recommendation === "hire";
                const isBorderline = interview.recommendation === "borderline";

                return (
                  <div
                    key={interview.id}
                    className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-muted/40 transition-colors"
                  >
                    <div className="flex items-center gap-3.5">
                      <div className="w-10 h-10 rounded-xl bg-cyan-950/80 border border-cyan-800/80 flex items-center justify-center font-mono font-bold text-xs text-cyan-300">
                        {typeof interview.overall_score === "number"
                          ? interview.overall_score.toFixed(1)
                          : "-"}
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
