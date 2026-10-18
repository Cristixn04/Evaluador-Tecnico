"use client";

import React, { useState } from "react";
import type { EvaluationReport } from "@/lib/api/client";
import {
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Quote,
  Sparkles,
  Copy,
  Check,
  Filter,
  ShieldCheck,
  X,
} from "lucide-react";

interface EvidencePanelProps {
  report: EvaluationReport;
  selectedCompetency: string | null;
  onSelectCompetency: (competency: string | null) => void;
}

export function EvidencePanel({
  report,
  selectedCompetency,
  onSelectCompetency,
}: EvidencePanelProps) {
  const [copiedQuestionIndex, setCopiedQuestionIndex] = useState<number | null>(null);

  const handleCopyQuestion = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedQuestionIndex(index);
    setTimeout(() => setCopiedQuestionIndex(null), 2000);
  };

  // Filtrar evidencias según la competencia seleccionada
  const filteredEvidence = selectedCompetency
    ? report.evidence.filter(
        (ev) =>
          ev.competency.toLowerCase() === selectedCompetency.toLowerCase() ||
          selectedCompetency.toLowerCase().includes(ev.competency.toLowerCase())
      )
    : report.evidence;

  return (
    <div className="space-y-6">
      {/* Alerta de Discrepancia / Revisión Humana */}
      {report.needs_human_review && (
        <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-600/50 flex items-start gap-3 text-amber-200">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-semibold text-amber-100">
              Requiere Revisión Humana Prioritaria
            </p>
            <p className="text-amber-300/90 text-xs mt-0.5">
              {report.discrepancy_note ||
                "Se detectó una discrepancia entre los evaluadores o puntajes fronterizos que requieren confirmación manual del Tech Lead."}
            </p>
          </div>
        </div>
      )}

      {/* Selector de Competencias Rápidas */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
              Desglose de Competencias
            </h3>
          </div>
          {selectedCompetency && (
            <button
              onClick={() => onSelectCompetency(null)}
              className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
              Limpiar filtro
            </button>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {Object.entries(report.competencies).map(([name, score]) => {
            const isSelected = selectedCompetency === name;
            const percentage = Math.round((score / 5) * 100);

            return (
              <button
                key={name}
                onClick={() =>
                  onSelectCompetency(isSelected ? null : name)
                }
                className={`p-3 rounded-lg border text-left transition-all ${
                  isSelected
                    ? "bg-cyan-950/60 border-cyan-500 shadow-[0_0_12px_rgba(6,182,212,0.25)]"
                    : "bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-850"
                }`}
              >
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span
                    className={`font-medium truncate ${
                      isSelected ? "text-cyan-200 font-semibold" : "text-slate-300"
                    }`}
                  >
                    {name}
                  </span>
                  <span className="font-mono text-cyan-400 font-bold ml-1">
                    {score.toFixed(1)}
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      score >= 4
                        ? "bg-cyan-400"
                        : score >= 3
                        ? "bg-amber-400"
                        : "bg-rose-400"
                    }`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Lista de Evidencias Auditables */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <h3 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">
              Evidencias Auditables Vinculadas
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            {filteredEvidence.length} evidencia(s) citada(s)
          </span>
        </div>

        {filteredEvidence.length === 0 ? (
          <div className="p-6 rounded-xl bg-slate-900/40 border border-slate-800 text-center text-sm text-slate-400">
            No se encontraron evidencias para la dimensión seleccionada.
          </div>
        ) : (
          <div className="space-y-3">
            {filteredEvidence.map((ev, idx) => (
              <div
                key={idx}
                className="p-4 rounded-xl bg-slate-900/70 border border-slate-800/80 hover:border-slate-700 transition-all space-y-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800/60">
                      {ev.competency}
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-400 border border-slate-700/60">
                      Ref: {ev.turn_id}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 text-xs font-semibold text-cyan-400">
                    <span>Nota:</span>
                    <span className="px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-800/80 font-mono">
                      {ev.score}/5
                    </span>
                  </div>
                </div>

                {/* Cita Textual de la Evidencia */}
                <div className="p-3 rounded-lg bg-slate-950/70 border border-slate-800/60 relative pl-9 text-xs text-slate-200 italic leading-relaxed">
                  <Quote className="w-4 h-4 text-cyan-500/70 absolute left-3 top-3" />
                  &ldquo;{ev.evidence_quote}&rdquo;
                </div>

                {/* Razonamiento Técnico del Evaluador */}
                {ev.reasoning && (
                  <div className="text-xs text-slate-300/90 leading-relaxed pl-1">
                    <span className="font-semibold text-slate-400 mr-1">
                      Evaluación Técnica:
                    </span>
                    {ev.reasoning}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Fortalezas y Riesgos */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Fortalezas */}
        <div className="p-4 rounded-xl bg-emerald-950/20 border border-emerald-800/40 space-y-2.5">
          <div className="flex items-center gap-2 text-emerald-400 text-xs font-semibold uppercase tracking-wider">
            <CheckCircle2 className="w-4 h-4" />
            <span>Fortalezas Clave</span>
          </div>
          <ul className="space-y-2">
            {(report.strengths || []).map((str, i) => (
              <li
                key={i}
                className="text-xs text-emerald-200/90 flex items-start gap-2 leading-relaxed"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0 mt-1.5" />
                <span>{str}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Riesgos / Puntos de Atención */}
        <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-800/40 space-y-2.5">
          <div className="flex items-center gap-2 text-amber-400 text-xs font-semibold uppercase tracking-wider">
            <AlertTriangle className="w-4 h-4" />
            <span>Riesgos y Áreas de Atención</span>
          </div>
          <ul className="space-y-2">
            {(report.risks || []).map((risk, i) => (
              <li
                key={i}
                className="text-xs text-amber-200/90 flex items-start gap-2 leading-relaxed"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0 mt-1.5" />
                <span>{risk}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Preguntas Sugeridas para la Entrevista Humana */}
      {report.suggested_human_questions &&
        report.suggested_human_questions.length > 0 && (
          <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-purple-400">
                <Sparkles className="w-4 h-4" />
                <h3 className="text-sm font-semibold text-slate-100 uppercase tracking-wider">
                  Guía para la Entrevista Humana (Tech Lead)
                </h3>
              </div>
              <span className="text-xs text-purple-300 bg-purple-950/80 px-2 py-0.5 rounded-full border border-purple-800/60 font-medium">
                Profundización
              </span>
            </div>

            <p className="text-xs text-slate-400">
              Preguntas generadas por la IA basadas en los puntos ciegos o decisiones tomadas por el candidato durante la prueba:
            </p>

            <div className="space-y-2.5 pt-1">
              {report.suggested_human_questions.map((q, i) => (
                <div
                  key={i}
                  className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 flex items-start justify-between gap-3 text-xs text-slate-200 group hover:border-purple-600/40 transition-colors"
                >
                  <div className="flex items-start gap-2.5">
                    <span className="font-mono text-purple-400 font-bold shrink-0 mt-0.5">
                      #{i + 1}
                    </span>
                    <span className="leading-relaxed">{q}</span>
                  </div>
                  <button
                    onClick={() => handleCopyQuestion(q, i)}
                    className="p-1.5 rounded text-slate-400 hover:text-purple-300 hover:bg-purple-950/60 transition-colors shrink-0"
                    title="Copiar pregunta"
                  >
                    {copiedQuestionIndex === i ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
    </div>
  );
}
