"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { InterviewPhase } from "@evaluador/contracts";
import {
  Clock,
  Wifi,
  WifiOff,
  Sparkles,
  ArrowRight,
  Code2,
  CheckCircle,
  HelpCircle,
  Cpu,
  FileText,
  AlertTriangle,
  Loader2,
} from "lucide-react";

interface InterviewHeaderProps {
  phase: InterviewPhase;
  candidateMaskedId: string;
  timeRemainingSeconds: number;
  connectionStatus: "connected" | "connecting" | "reconnecting" | "simulated";
  onTransitionPhase: (nextPhase: InterviewPhase) => void;
  availableTransitions?: InterviewPhase[];
}

const PHASES: Array<{ id: InterviewPhase; label: string; icon: any }> = [
  { id: "PROBLEM", label: "1. Enunciado", icon: FileText },
  { id: "CLARIFY", label: "2. Aclaración", icon: HelpCircle },
  { id: "DESIGN", label: "3. Diseño", icon: Cpu },
  { id: "CODING", label: "4. Código", icon: Code2 },
  { id: "PROBE", label: "5. Sondeo", icon: Sparkles },
  { id: "WRAPUP", label: "6. Cierre", icon: CheckCircle },
];

export function InterviewHeader({
  phase,
  candidateMaskedId,
  timeRemainingSeconds,
  connectionStatus,
  onTransitionPhase,
  availableTransitions,
}: InterviewHeaderProps) {
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const getNextTransition = () => {
    switch (phase) {
      case "INTRO":
        return { label: "Ver problema", target: "PROBLEM" as InterviewPhase };
      case "PROBLEM":
        return { label: "Hacer preguntas al evaluador", target: "CLARIFY" as InterviewPhase };
      case "CLARIFY":
        return { label: "Listo para diseñar", target: "DESIGN" as InterviewPhase };
      case "DESIGN":
        return { label: "Empezar a programar", target: "CODING" as InterviewPhase };
      case "CODING":
        return { label: "Pasar a preguntas de sondeo", target: "PROBE" as InterviewPhase };
      case "PROBE":
        return { label: "Finalizar prueba técnica", target: "WRAPUP" as InterviewPhase };
      case "WRAPUP":
        return null;
      default:
        return null;
    }
  };

  const nextTransition = getNextTransition();

  return (
    <>
      <header className="h-16 border-b border-border/50 bg-background/95 backdrop-blur px-6 flex items-center justify-between shrink-0">
      {/* Left: Branding & Candidate Code */}
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-bold text-xs">
          ET
        </div>
        <div>
          <span className="font-bold text-sm tracking-tight hidden md:inline">
            Sala de Evaluación Técnica
          </span>
          <div className="flex items-center gap-2 mt-0.5">
            <Badge variant="outline" className="font-mono text-[10px] text-muted-foreground">
              {candidateMaskedId}
            </Badge>
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
              {connectionStatus === "connected" ? (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="text-emerald-500 hidden sm:inline">En vivo</span>
                </>
              ) : (
                <>
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
                  <span className="text-blue-400 hidden sm:inline">Modo interactivo</span>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Center: Phase Stepper */}
      <div className="hidden lg:flex items-center gap-1 bg-muted/20 p-1 rounded-lg border border-border/40">
        {PHASES.map((p, idx) => {
          const isCurrent = phase === p.id;
          const currentIdx = PHASES.findIndex((item) => item.id === phase);
          const isPassed = currentIdx !== -1 && currentIdx > idx;
          const isAvailable = availableTransitions
            ? availableTransitions.includes(p.id)
            : nextTransition?.target === p.id;

          if (isAvailable && !isCurrent && !isPassed) {
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => onTransitionPhase(p.id)}
                title={`Avanzar a ${p.label}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-all text-primary hover:bg-primary/20 border border-primary/40 cursor-pointer shadow-sm hover:scale-[1.02]"
              >
                <p.icon className="h-3.5 w-3.5" />
                <span>{p.label}</span>
              </button>
            );
          }

          return (
            <div
              key={p.id}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                isCurrent
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : isPassed
                  ? "text-emerald-400"
                  : "text-muted-foreground/60"
              }`}
            >
              <p.icon className="h-3.5 w-3.5" />
              <span>{p.label}</span>
            </div>
          );
        })}
      </div>

      {/* Right: Timer & Transition Action */}
      <div className="flex items-center gap-3">
        {/* Timer */}
        <div className="flex items-center gap-1.5 bg-muted/30 border border-border/50 px-2.5 py-1 rounded-md font-mono text-xs">
          <Clock className={`h-3.5 w-3.5 ${timeRemainingSeconds < 300 ? "text-destructive animate-pulse" : "text-primary"}`} />
          <span className={timeRemainingSeconds < 300 ? "text-destructive font-bold" : "text-foreground"}>
            {formatTime(timeRemainingSeconds)}
          </span>
        </div>

        {/* Regular Phase Transition Button (for phases before WRAPUP) */}
        {nextTransition && (
          <Button
            size="sm"
            onClick={() => onTransitionPhase(nextTransition.target)}
            className="h-8 text-xs gap-1.5 bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm"
          >
            <span>{nextTransition.label}</span>
            <ArrowRight className="h-3 w-3" />
          </Button>
        )}

        {/* Finish Interview Button: ONLY visible in WRAPUP */}
        {phase === "WRAPUP" && (
          <Button
            size="sm"
            id="finish-interview-btn"
            onClick={() => setShowConfirmModal(true)}
            disabled={isSubmitting || (connectionStatus !== "connected" && connectionStatus !== "simulated")}
            className="h-8 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm font-semibold cursor-pointer"
          >
            <CheckCircle className="h-3.5 w-3.5" />
            <span>Entregar y Finalizar Entrevista</span>
          </Button>
        )}
      </div>
    </header>

    {/* Confirmation Modal */}
    {showConfirmModal && phase === "WRAPUP" && (
      <div
        id="closure-modal-backdrop"
        className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150"
      >
        <div
          id="closure-modal"
          className="bg-card border border-border rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4"
        >
          <div className="flex items-center gap-3 text-amber-500">
            <div className="h-10 w-10 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-foreground">
                ¿Confirmas la entrega definitiva?
              </h3>
              <p className="text-xs text-muted-foreground">
                Finalización formal de la evaluación técnica
              </p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed">
            Al confirmar, tu sesión se dará por <strong>finalizada formalmente</strong>. No podrás volver a editar tu solución, ejecutar pruebas ni enviar mensajes adicionales en el chat. Esta acción es <strong>definitiva</strong>.
          </p>

          <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border/40">
            <Button
              variant="outline"
              size="sm"
              id="cancel-closure-btn"
              onClick={() => setShowConfirmModal(false)}
              disabled={isSubmitting}
              className="text-xs cursor-pointer"
            >
              Cancelar y seguir en Cierre
            </Button>
            <Button
              size="sm"
              id="confirm-closure-btn"
              onClick={() => {
                if (isSubmitting) return;
                setIsSubmitting(true);
                onTransitionPhase("EVALUATE");
              }}
              disabled={isSubmitting || (connectionStatus !== "connected" && connectionStatus !== "simulated")}
              className="text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Entregando...</span>
                </>
              ) : (
                <>
                  <CheckCircle className="h-3.5 w-3.5" />
                  <span>Confirmar y Finalizar</span>
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    )}
  </>
  );
}
