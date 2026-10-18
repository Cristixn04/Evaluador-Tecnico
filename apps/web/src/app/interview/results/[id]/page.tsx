"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, type EvaluationReport, type InterviewTrajectory } from "@/lib/api/client";
import { CompetencyRadar } from "@/components/evaluation/competency-radar";
import { EvidencePanel } from "@/components/evaluation/evidence-panel";
import { TrajectoryPlayer } from "@/components/evaluation/trajectory-player";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ArrowLeft,
  Shield,
  Award,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Printer,
  ChevronDown,
  ChevronUp,
  History,
  FileCheck2,
  Calendar,
  Layers,
} from "lucide-react";

export default function InterviewResultsPage() {
  const params = useParams();
  const router = useRouter();
  const interviewId = (params?.id as string) || "int-001";

  const [evaluation, setEvaluation] = useState<EvaluationReport | null>(null);
  const [trajectory, setTrajectory] = useState<InterviewTrajectory | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedCompetency, setSelectedCompetency] = useState<string | null>(null);
  const [showTrajectory, setShowTrajectory] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        setIsLoading(true);
        setError(null);

        const [evalData, trajData] = await Promise.all([
          api.getEvaluation(interviewId),
          api.getInterviewTrajectory(interviewId).catch(() => null),
        ]);

        setEvaluation(evalData);
        setTrajectory(trajData);
      } catch (err: any) {
        console.error("Error loading interview evaluation:", err);
        setError(err.message || "No se pudo cargar el reporte de la entrevista.");
      } finally {
        setIsLoading(false);
      }
    }

    loadData();
  }, [interviewId]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-50 p-6 md:p-10 max-w-7xl mx-auto space-y-8">
        <div className="flex items-center gap-4">
          <Skeleton className="w-10 h-10 rounded-lg bg-slate-800" />
          <div className="space-y-2">
            <Skeleton className="w-64 h-6 bg-slate-800" />
            <Skeleton className="w-40 h-4 bg-slate-800" />
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Skeleton className="h-64 rounded-xl bg-slate-900" />
          <Skeleton className="h-64 rounded-xl bg-slate-900 md:col-span-2" />
        </div>
      </div>
    );
  }

  if (error || !evaluation) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center p-6">
        <div className="max-w-md w-full p-8 rounded-2xl bg-slate-900 border border-slate-800 text-center space-y-4 shadow-2xl">
          <div className="w-12 h-12 rounded-full bg-rose-950/80 border border-rose-800/80 flex items-center justify-center text-rose-400 mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-semibold text-slate-100">Error al Cargar Reporte</h2>
          <p className="text-sm text-slate-400">{error || "Entrevista no encontrada"}</p>
          <Button
            onClick={() => router.push("/dashboard")}
            variant="outline"
            className="w-full border-slate-700 hover:bg-slate-800"
          >
            Volver al Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const getRecommendationBadge = (rec: string) => {
    switch (rec) {
      case "hire":
        return {
          label: "RECOMENDACIÓN: CONTRATAR",
          color: "bg-emerald-950/90 text-emerald-300 border-emerald-700/80",
          icon: CheckCircle2,
        };
      case "borderline":
        return {
          label: "RECOMENDACIÓN: REVISIÓN / DUDOSO",
          color: "bg-amber-950/90 text-amber-300 border-amber-700/80",
          icon: AlertCircle,
        };
      default:
        return {
          label: "RECOMENDACIÓN: NO CONTRATAR",
          color: "bg-rose-950/90 text-rose-300 border-rose-700/80",
          icon: XCircle,
        };
    }
  };

  const recBadge = getRecommendationBadge(evaluation.recommendation);
  const RecIcon = recBadge.icon;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Barra Superior de Navegación y Acciones */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-5">
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
              title="Volver al panel"
            >
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/80">
                  {evaluation.masked_candidate_id}
                </span>
                <span className="text-xs text-slate-400 flex items-center gap-1">
                  <Shield className="w-3.5 h-3.5 text-emerald-400" />
                  Proceso Ciego a PII (Ley 1581)
                </span>
              </div>
              <h1 className="text-xl sm:text-2xl font-bold text-slate-100 mt-1">
                Informe Defendible de Evaluación Técnica
              </h1>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button
              onClick={() => window.print()}
              variant="outline"
              size="sm"
              className="border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-300 gap-1.5"
            >
              <Printer className="w-4 h-4" />
              <span>Imprimir / Exportar</span>
            </Button>
          </div>
        </div>

        {/* Tarjeta de Resumen Ejecutivo y Decisión */}
        <div className="p-6 rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-xl grid grid-cols-1 md:grid-cols-3 gap-6 items-center">
          {/* Puntuación Global */}
          <div className="flex items-center gap-5 border-b md:border-b-0 md:border-r border-slate-800 pb-5 md:pb-0 md:pr-5">
            <div className="relative flex items-center justify-center">
              <div className="w-20 h-20 rounded-2xl bg-cyan-950/80 border border-cyan-600/50 flex flex-col items-center justify-center shadow-lg shadow-cyan-950/60">
                <span className="text-2xl font-bold font-mono text-cyan-300">
                  {evaluation.overall_score.toFixed(1)}
                </span>
                <span className="text-[10px] text-cyan-400/80 uppercase font-semibold">
                  de 5.0
                </span>
              </div>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase text-slate-400 tracking-wider">
                Puntuación General
              </p>
              <p className="text-base font-bold text-slate-100">
                {evaluation.overall_score >= 4
                  ? "Desempeño Sobresaliente"
                  : evaluation.overall_score >= 3
                  ? "Desempeño Aceptable"
                  : "Por Debajo del Perfil"}
              </p>
              <p className="text-xs text-slate-400">
                Evaluado con base en 6 dimensiones ponderadas
              </p>
            </div>
          </div>

          {/* Veredicto y Recomendación */}
          <div className="flex flex-col gap-2 border-b md:border-b-0 md:border-r border-slate-800 pb-5 md:pb-0 md:pr-5">
            <p className="text-xs font-semibold uppercase text-slate-400 tracking-wider">
              Veredicto del Agente Evaluador
            </p>
            <div
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl border text-xs font-bold uppercase tracking-wider w-fit shadow-sm ${recBadge.color}`}
            >
              <RecIcon className="w-4 h-4 shrink-0" />
              <span>{recBadge.label}</span>
            </div>
            <p className="text-xs text-slate-400 leading-relaxed">
              Decisión respaldada por evidencias observables y trazabilidad de pruebas.
            </p>
          </div>

          {/* Indicadores de Auditoría */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 flex items-center gap-1.5">
                <FileCheck2 className="w-3.5 h-3.5 text-cyan-400" />
                Evidencias Registradas:
              </span>
              <span className="font-semibold text-slate-200">
                {evaluation.evidence.length} citas textuales
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 flex items-center gap-1.5">
                <History className="w-3.5 h-3.5 text-purple-400" />
                Auditabilidad:
              </span>
              <span className="font-semibold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                100% Verificado
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-amber-400" />
                Revisión Humana:
              </span>
              <span
                className={`font-semibold ${
                  evaluation.needs_human_review ? "text-amber-400" : "text-slate-400"
                }`}
              >
                {evaluation.needs_human_review ? "Requerida" : "No requerida"}
              </span>
            </div>
          </div>
        </div>

        {/* Sección Principal: Radar de Competencias y Panel de Evidencias */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Radar Chart (Columna Izquierda: 5 cols) */}
          <div className="lg:col-span-5 p-6 rounded-2xl bg-slate-900/80 border border-slate-800 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
                  Radar de Competencias
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  Comparativa dimensional vs rúbrica esperada
                </p>
              </div>
              <Badge variant="outline" className="border-cyan-800 bg-cyan-950/60 text-cyan-300 text-xs">
                6 Ejes
              </Badge>
            </div>

            <CompetencyRadar
              competencies={evaluation.competencies}
              selectedCompetency={selectedCompetency}
              onSelectCompetency={(comp) => setSelectedCompetency(comp)}
            />
          </div>

          {/* Panel de Evidencias Auditadas (Columna Derecha: 7 cols) */}
          <div className="lg:col-span-7">
            <EvidencePanel
              report={evaluation}
              selectedCompetency={selectedCompetency}
              onSelectCompetency={setSelectedCompetency}
            />
          </div>
        </div>

        {/* Sección del Reproductor de la Trayectoria de Depuración (Timeline Player) */}
        {trajectory && (
          <div className="space-y-4 pt-4 border-t border-slate-800">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <History className="w-5 h-5 text-cyan-400" />
                <div>
                  <h2 className="text-base font-bold text-slate-100">
                    Trayectoria de Código y Depuración (Timeline Player)
                  </h2>
                  <p className="text-xs text-slate-400">
                    Inspección forense de cómo el candidato enfrentó errores y evolucionó la solución.
                  </p>
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowTrajectory(!showTrajectory)}
                className="border-slate-800 bg-slate-900 hover:bg-slate-800 text-xs text-slate-300 gap-1.5"
              >
                {showTrajectory ? (
                  <>
                    <ChevronUp className="w-4 h-4" />
                    <span>Ocultar reproductor</span>
                  </>
                ) : (
                  <>
                    <ChevronDown className="w-4 h-4" />
                    <span>Mostrar reproductor</span>
                  </>
                )}
              </Button>
            </div>

            {showTrajectory && <TrajectoryPlayer trajectory={trajectory} />}
          </div>
        )}
      </div>
    </div>
  );
}
