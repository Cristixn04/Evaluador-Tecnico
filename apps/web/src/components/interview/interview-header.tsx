"use client";

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
} from "lucide-react";

interface InterviewHeaderProps {
  phase: InterviewPhase;
  candidateMaskedId: string;
  timeRemainingSeconds: number;
  connectionStatus: "connected" | "connecting" | "reconnecting" | "simulated";
  onTransitionPhase: (nextPhase: InterviewPhase) => void;
}

const PHASES: Array<{ id: InterviewPhase; label: string; icon: any }> = [
  { id: "CLARIFY", label: "1. Aclaración", icon: HelpCircle },
  { id: "DESIGN", label: "2. Diseño", icon: Cpu },
  { id: "CODING", label: "3. Código", icon: Code2 },
  { id: "PROBE", label: "4. Sondeo", icon: Sparkles },
  { id: "WRAPUP", label: "5. Cierre", icon: CheckCircle },
];

export function InterviewHeader({
  phase,
  candidateMaskedId,
  timeRemainingSeconds,
  connectionStatus,
  onTransitionPhase,
}: InterviewHeaderProps) {
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const getNextTransition = () => {
    switch (phase) {
      case "INTRO":
      case "PROBLEM":
      case "CLARIFY":
        return { label: "Listo para diseñar", target: "DESIGN" as InterviewPhase };
      case "DESIGN":
        return { label: "Empezar a programar", target: "CODING" as InterviewPhase };
      case "CODING":
        return { label: "Pasar a preguntas de sondeo", target: "PROBE" as InterviewPhase };
      case "PROBE":
        return { label: "Finalizar prueba técnica", target: "WRAPUP" as InterviewPhase };
      default:
        return null;
    }
  };

  const nextTransition = getNextTransition();

  return (
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
          const isPassed =
            PHASES.findIndex((item) => item.id === phase) > idx;

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

        {/* Phase Transition Button */}
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
      </div>
    </header>
  );
}
