"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useInterviewSocket } from "@/lib/hooks/use-interview-socket";
import { useDebouncedSnapshot } from "@/lib/hooks/use-debounced-snapshot";
import { InterviewHeader } from "@/components/interview/interview-header";
import { ProblemViewer } from "@/components/interview/problem-viewer";
import { ChatPanel } from "@/components/interview/chat-panel";
import { CodeEditor } from "@/components/interview/code-editor";
import { TestConsole } from "@/components/interview/test-console";
import { api } from "@/lib/api/client";
import type { CodeLanguage } from "@evaluador/contracts";
import {
  ShieldCheck,
  Sparkles,
  HelpCircle,
  FileText,
  MessageSquare,
  ArrowRight,
  Loader2,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

function InterviewContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "cand-demo-token-123";
  const [sessionData, setSessionData] = useState<any>(null);
  const [isVerifying, setIsVerifying] = useState(true);
  const [verificationError, setVerificationError] = useState<string | null>(null);

  const [hasConsented, setHasConsented] = useState(false);
  const [activeLeftTab, setActiveLeftTab] = useState<"chat" | "problem">("chat");
  const [code, setCode] = useState("");
  const [language, setLanguage] = useState<CodeLanguage>("python");
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving">("saved");

  useEffect(() => {
    async function verify() {
      if (!token) {
        setVerificationError("No se proporcionó ningún token en el enlace.");
        setIsVerifying(false);
        return;
      }
      try {
        const data = await api.verifyCandidateSession(token);
        setSessionData(data);
        if (data.problem?.language) {
          setLanguage(data.problem.language as CodeLanguage);
        }
      } catch (err: any) {
        setVerificationError(
          "El enlace de evaluación no es válido o ha expirado. Por favor solicita un nuevo enlace a tu reclutador."
        );
      } finally {
        setIsVerifying(false);
      }
    }
    verify();
  }, [token]);

  const candidateMaskedId = sessionData?.masked_candidate_id || "CAND-7F2A";
  const problemData = sessionData?.problem || {
    id: "prob-pse-conciliacion",
    title: "Conciliación de Pagos PSE y Liquidación Bancaria",
    difficulty: "senior",
    language: "python",
    scenario_preview:
      "Una pasarela de pagos fintech colombiana experimenta discrepancias de redondeo y transacciones huérfanas en conciliaciones de lotes ACH. Diseña el algoritmo de conciliación.",
    tags: ["Fintech", "PSE", "ACH", "Algoritmos", "Idempotencia"],
  };

  const socket = useInterviewSocket({
    interviewId: sessionData?.session_id || "sess-live-999",
    token,
    candidateMaskedId,
    problemTitle: problemData.title,
    initialPhase: "INTRO",
    wsUrl: sessionData?.ws_url,
    wsToken: sessionData?.ws_token,
  });

  // Hook de snapshots automáticos de la trayectoria
  const { triggerImmediateSnapshot } = useDebouncedSnapshot({
    code,
    language,
    enabled: hasConsented,
    onSnapshot: (currentCode, lang, reason) => {
      setSaveStatus("saving");
      socket.sendCodeSnapshot(currentCode, lang, reason);
      setTimeout(() => setSaveStatus("saved"), 400);
    },
    debounceMs: 3500,
  });

  // Monitoreo ético de integridad (blur y pegado masivo)
  useEffect(() => {
    if (!hasConsented) return;

    const handleBlur = () => {
      socket.sendIntegrityEvent("blur");
      triggerImmediateSnapshot("blur");
    };

    const handleFocus = () => {
      socket.sendIntegrityEvent("focus");
    };

    const handlePaste = (e: ClipboardEvent) => {
      const text = e.clipboardData?.getData("text") || "";
      if (text.length > 150) {
        socket.sendIntegrityEvent("paste_large", { pasted_length: text.length });
      }
    };

    window.addEventListener("blur", handleBlur);
    window.addEventListener("focus", handleFocus);
    window.addEventListener("paste", handlePaste);

    return () => {
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("paste", handlePaste);
    };
  }, [hasConsented, socket, triggerImmediateSnapshot]);

  // Manejar inicio de la entrevista tras aceptar consentimiento
  const handleStartInterview = () => {
    setHasConsented(true);
    socket.requestPhaseTransition("CLARIFY");
  };

  // Manejar ejecución de pruebas
  const handleRunTests = () => {
    triggerImmediateSnapshot("run");
    socket.runCode(code, language);
  };

  // 0. Estado de carga durante verificación de token
  if (isVerifying) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-background">
        <div className="flex items-center gap-3 text-sm text-muted-foreground font-mono">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <span>Verificando enlace de evaluación y credenciales anónimas...</span>
        </div>
      </div>
    );
  }

  // 0.1 Error de verificación (Token inválido o expirado)
  if (verificationError) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gradient-to-b from-background to-muted/20">
        <div className="w-full max-w-md">
          <Card className="border-destructive/40 shadow-xl">
            <CardHeader className="text-center space-y-2">
              <div className="h-10 w-10 rounded-full bg-destructive/10 text-destructive flex items-center justify-center mx-auto">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <CardTitle className="text-lg">Enlace No Válido o Expirado</CardTitle>
              <CardDescription className="text-xs">
                {verificationError}
              </CardDescription>
            </CardHeader>
            <CardFooter className="flex justify-center">
              <Link href="/">
                <Button variant="outline" size="sm">
                  Volver al inicio
                </Button>
              </Link>
            </CardFooter>
          </Card>
        </div>
      </div>
    );
  }

  // 1. Pantalla Inicial de Reglas y Consentimiento (Fase INTRO)
  if (!hasConsented) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gradient-to-b from-background to-muted/20">
        <div className="w-full max-w-2xl space-y-6">
          <Card className="border-border/80 shadow-2xl">
            <CardHeader className="space-y-2 pb-4">
              <div className="flex items-center justify-between">
                <Badge variant="outline" className="font-mono text-xs text-primary border-primary/30">
                  {candidateMaskedId}
                </Badge>
                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                  <ShieldCheck className="h-4 w-4" />
                  <span>Evaluación Ciega a Sesgos</span>
                </div>
              </div>
              <CardTitle className="text-2xl font-bold tracking-tight">
                Entrevista Técnica Inicial Asistida por IA
              </CardTitle>
              <CardDescription className="text-sm leading-relaxed">
                Vas a resolver el problema: <strong className="text-foreground">{problemData.title}</strong>.
              </CardDescription>
            </CardHeader>

            <CardContent className="space-y-4 text-xs sm:text-sm">
              <div className="p-4 rounded-lg bg-muted/40 border border-border/60 space-y-2">
                <span className="font-bold text-foreground block">
                  💡 ¿Cómo funciona esta entrevista?
                </span>
                <p className="text-muted-foreground leading-relaxed">
                  No estás ante un test automatizado tradicional de acierto o fallo. Nuestro agente evalúa tu <strong>razonamiento, diseño y cómo depuras tu código</strong> ante situaciones imprevistas.
                </p>
              </div>

              <div className="space-y-2.5">
                <span className="font-semibold text-foreground text-xs uppercase tracking-wider block">
                  Fases de la Sesión (45 minutos):
                </span>
                <ol className="space-y-2 text-xs text-muted-foreground">
                  <li className="flex items-start gap-2">
                    <span className="h-5 w-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold shrink-0">1</span>
                    <span><strong>Aclaración:</strong> Lee el enunciado y hazle preguntas al evaluador sobre requerimientos y casos borde.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="h-5 w-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold shrink-0">2</span>
                    <span><strong>Diseño:</strong> Explica tu estrategia algorítmica y complejidad antes de programar.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="h-5 w-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold shrink-0">3</span>
                    <span><strong>Codificación:</strong> Escribe tu solución en el editor Monaco y ejecuta pruebas en el sandbox.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="h-5 w-5 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold shrink-0">4</span>
                    <span><strong>Sondeo:</strong> El evaluador te hará preguntas específicas sobre las decisiones que tomaste en tu código.</span>
                  </li>
                </ol>
              </div>

              <div className="p-3 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-xs text-emerald-300 leading-relaxed flex items-start gap-2.5">
                <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-emerald-400" />
                <span>
                  <strong>Garantía de Equidad (Ley 1581):</strong> Tus datos personales (nombre, género, foto, universidad) no son visibles para el agente evaluador. La sesión es calificada con base exclusiva en evidencia técnica defendible.
                </span>
              </div>
            </CardContent>

            <CardFooter className="pt-2">
              <Button size="lg" className="w-full gap-2 text-sm font-semibold" onClick={handleStartInterview}>
                <span>Entiendo las Reglas y Deseo Comenzar</span>
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
    );
  }

  // 2. Sala de Entrevista Activa (Split Screen)
  return (
    <div className="h-screen w-screen flex flex-col bg-background overflow-hidden">
      {/* Top Header */}
      <InterviewHeader
        phase={socket.phase}
        candidateMaskedId={candidateMaskedId}
        timeRemainingSeconds={socket.timeRemaining}
        connectionStatus={socket.connectionStatus}
        onTransitionPhase={socket.requestPhaseTransition}
      />

      {/* Main Split-Screen Workspace */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
        {/* Left Panel: Chat & Problem Tabs (45% width) */}
        <div className="w-full md:w-[45%] lg:w-[42%] flex flex-col border-r border-border/50 h-full overflow-hidden bg-card/30">
          {/* Tab Selector */}
          <div className="h-10 px-4 bg-muted/20 border-b border-border/40 flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setActiveLeftTab("chat")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                activeLeftTab === "chat"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5" />
              <span>Chat con el Evaluador</span>
              {socket.isStreaming && (
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveLeftTab("problem")}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors flex items-center gap-1.5 ${
                activeLeftTab === "problem"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>Enunciado del Problema</span>
            </button>
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-hidden">
            {activeLeftTab === "chat" ? (
              <ChatPanel
                messages={socket.messages}
                isStreaming={socket.isStreaming}
                onSendMessage={socket.sendMessage}
              />
            ) : (
              <ProblemViewer problem={problemData} />
            )}
          </div>
        </div>

        {/* Right Panel: Monaco Editor & Test Console (55% width) */}
        <div className="w-full md:w-[55%] lg:w-[58%] flex flex-col h-full overflow-hidden bg-[#1e1e1e]">
          {/* Top: Editor (65% height) */}
          <div className="flex-1 min-h-[350px] overflow-hidden">
            <CodeEditor
              code={code}
              language={language}
              onChangeCode={setCode}
              onLanguageChange={setLanguage}
              onRunTests={handleRunTests}
              isRunningTests={socket.isRunningTests}
              saveStatus={saveStatus}
            />
          </div>

          {/* Bottom: Test Console (35% height) */}
          <div className="h-[220px] lg:h-[250px] shrink-0">
            <TestConsole
              result={socket.testResult}
              isRunning={socket.isRunningTests}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LiveInterviewPage() {
  return (
    <Suspense
      fallback={
        <div className="h-screen w-screen flex items-center justify-center bg-background">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
        </div>
      }
    >
      <InterviewContent />
    </Suspense>
  );
}
