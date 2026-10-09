import { useState, useEffect, useRef, useCallback } from "react";
import type {
  InterviewPhase,
  CodeLanguage,
  SnapshotReason,
  IntegrityEventType,
  ClientWebSocketMessage,
  ServerWebSocketMessage,
  ServerCodeExecutionResultMessage,
} from "@evaluador/contracts";

export interface ChatMessage {
  id: string;
  speaker: "agent" | "candidate" | "system";
  content: string;
  timestamp: number;
}

interface UseInterviewSocketProps {
  interviewId: string;
  token: string;
  candidateMaskedId: string;
  problemTitle: string;
  initialPhase?: InterviewPhase;
  wsUrl?: string;
  wsToken?: string;
}

export function useInterviewSocket({
  interviewId,
  token,
  candidateMaskedId,
  problemTitle,
  initialPhase = "INTRO",
  wsUrl,
  wsToken,
}: UseInterviewSocketProps) {
  const [phase, setPhase] = useState<InterviewPhase>(initialPhase);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<
    "connected" | "connecting" | "reconnecting" | "simulated"
  >("simulated");
  const [timeRemaining, setTimeRemaining] = useState(2700); // 45 minutos por defecto
  const [testResult, setTestResult] = useState<ServerCodeExecutionResultMessage | null>(null);
  const [isRunningTests, setIsRunningTests] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const currentStreamingTurnId = useRef<string | null>(null);

  // Conexión WebSocket real con fallback suave a emulador
  useEffect(() => {
    if (!wsUrl || !wsToken) return;

    let ws: WebSocket | null = null;
    try {
      const fullUrl = `${wsUrl}?token=${encodeURIComponent(wsToken)}`;
      setConnectionStatus("connecting");
      ws = new WebSocket(fullUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        setConnectionStatus("connected");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "agent_token") {
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              if (last && last.id === data.turn_id) {
                return [
                  ...prev.slice(0, -1),
                  { ...last, content: last.content + data.delta },
                ];
              } else {
                return [
                  ...prev,
                  { id: data.turn_id, speaker: "agent", content: data.delta, timestamp: Date.now() },
                ];
              }
            });
          } else if (data.type === "agent_turn_complete") {
            setIsStreaming(false);
          } else if (data.type === "phase_changed") {
            setPhase(data.current_phase);
          } else if (data.type === "code_execution_result") {
            setTestResult(data);
            setIsRunningTests(false);
          } else if (data.type === "session_tick") {
            setTimeRemaining(data.time_remaining_seconds);
          }
        } catch (e) {
          console.error("Error parsing WS message", e);
        }
      };

      ws.onerror = () => {
        setConnectionStatus("simulated");
      };

      ws.onclose = () => {
        setConnectionStatus("simulated");
      };
    } catch {
      setConnectionStatus("simulated");
    }

    return () => {
      if (ws) ws.close();
    };
  }, [wsUrl, wsToken]);

  // Inicializar mensaje de bienvenida del agente
  useEffect(() => {
    if (messages.length === 0) {
      setMessages([
        {
          id: "turn-welcome",
          speaker: "agent",
          content: `¡Hola! Bienvenido a tu entrevista técnica para el rol de ingeniería. Estaremos trabajando en el problema "${problemTitle}". Puedes hacerme cualquier pregunta técnica o aclarar requerimientos antes de comenzar a escribir tu código. ¿Tienes alguna duda inicial sobre el enunciado?`,
          timestamp: Date.now(),
        },
      ]);
    }
  }, [problemTitle, messages.length]);

  // Temporizador de sesión
  useEffect(() => {
    if (phase === "INTRO" || phase === "EVALUATE") return;
    const interval = setInterval(() => {
      setTimeRemaining((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [phase]);

  // Emulador de respuestas en streaming para desarrollo interactivo
  const emulateAgentResponse = useCallback(
    async (candidateText: string, currentPhase: InterviewPhase) => {
      setIsStreaming(true);
      const turnId = `turn-${Date.now()}`;
      currentStreamingTurnId.current = turnId;

      let fullResponse = "";
      if (currentPhase === "CLARIFY" || currentPhase === "PROBLEM") {
        fullResponse = `Excelente pregunta. En este escenario, el volumen esperado es de aproximadamente 50.000 transacciones por lote ACH y debemos garantizar idempotencia para evitar cargos duplicados. Cuando sientas que tienes los requerimientos claros, puedes hacer clic en "Listo para diseñar" en la barra superior para explicar tu estrategia.`;
      } else if (currentPhase === "DESIGN") {
        fullResponse = `Me parece un enfoque muy sólido. La descomposición modular que planteas separa bien la validación de montos del cálculo de conciliación. ¿Qué complejidad temporal estimas para la búsqueda de transacciones huérfanas? Cuando estés listo, presiona "Empezar a programar" para abrir el editor.`;
      } else if (currentPhase === "CODING") {
        fullResponse = `Veo tu implementación en el editor. Recuerda revisar los casos borde, como transacciones con estados desconocidos o marcas de tiempo desfasadas. Puedes presionar "Ejecutar Pruebas" en cualquier momento para validar tus casos.`;
      } else if (currentPhase === "PROBE") {
        fullResponse = `Analizando tu código: observo que usaste un diccionario indexado por transacción en lugar de realizar una iteración anidada. ¿Por qué tomaste esa decisión de arquitectura y cómo afectaría la memoria si el lote crece a 5 millones de registros?`;
      } else {
        fullResponse = `Comprendo tu punto. Gracias por detallar tu proceso de razonamiento.`;
      }

      // Agregar mensaje vacío para empezar streaming
      setMessages((prev) => [
        ...prev,
        {
          id: turnId,
          speaker: "agent",
          content: "",
          timestamp: Date.now(),
        },
      ]);

      // Streaming de tokens palabra por palabra con retardo natural
      const words = fullResponse.split(" ");
      let accumulated = "";

      for (let i = 0; i < words.length; i++) {
        await new Promise((r) => setTimeout(r, 45));
        accumulated += (i > 0 ? " " : "") + words[i];
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === turnId ? { ...msg, content: accumulated } : msg
          )
        );
      }

      setIsStreaming(false);
      currentStreamingTurnId.current = null;
    },
    []
  );

  // 1. Enviar mensaje de chat
  const sendMessage = useCallback(
    (text: string) => {
      if (!text.trim()) return;

      const userMsg: ChatMessage = {
        id: `turn-cand-${Date.now()}`,
        speaker: "candidate",
        content: text.trim(),
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg]);

      // Si hay WebSocket real conectado, enviar trama
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        const payload: ClientWebSocketMessage = {
          type: "chat_message",
          content: text.trim(),
          client_timestamp: Date.now(),
        };
        socketRef.current.send(JSON.stringify(payload));
      } else {
        // Modo simulado interactivo
        setTimeout(() => {
          emulateAgentResponse(text, phase);
        }, 500);
      }
    },
    [phase, emulateAgentResponse]
  );

  // 2. Enviar snapshot de código
  const sendCodeSnapshot = useCallback(
    (code: string, language: CodeLanguage, reason: SnapshotReason) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        const payload: ClientWebSocketMessage = {
          type: "code_snapshot",
          code,
          language,
          reason,
          client_timestamp: Date.now(),
        };
        socketRef.current.send(JSON.stringify(payload));
      } else {
        // En modo simulado, solo registramos en consola silenciosa
        console.log(`[Trajectory Snapshot: ${reason}] ${code.length} chars`);
      }
    },
    []
  );

  // 3. Ejecutar código en sandbox
  const runCode = useCallback(
    (code: string, language: CodeLanguage) => {
      setIsRunningTests(true);

      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        const payload: ClientWebSocketMessage = {
          type: "run_code",
          code,
          language,
        };
        socketRef.current.send(JSON.stringify(payload));
      } else {
        // Emulación inmediata de ejecución de tests (Judge0 fallback)
        setTimeout(() => {
          const hasSolution = code.includes("return") || code.includes("def ");
          const passed = hasSolution ? 4 : 2;
          const total = 4;

          setTestResult({
            type: "code_execution_result",
            status: passed === total ? "success" : "test_failure",
            stdout: "Ejecutando suite de pruebas unitarias...\nTest 1 (Conciliación simple): OK\nTest 2 (Lote con discrepancia de centavos): OK\nTest 3 (Transacciones huérfanas ACH): " + (passed === 4 ? "OK" : "FAILED (AssertionError)") + "\nTest 4 (Idempotencia de transacción duplicada): " + (passed === 4 ? "OK" : "PENDING"),
            stderr: passed === total ? "" : "AssertionError: expected orphan_count == 1, got 0",
            execution_time_ms: 142,
            tests_passed: passed,
            total_tests: total,
            test_details: [
              { test_name: "test_simple_reconciliation", passed: true },
              { test_name: "test_cents_discrepancy", passed: true },
              { test_name: "test_orphan_transactions", passed: passed === 4, message: passed === 4 ? undefined : "Diferencia en recuento de huérfanas" },
              { test_name: "test_idempotent_duplicate", passed: passed === 4 },
            ],
          });
          setIsRunningTests(false);
        }, 1200);
      }
    },
    []
  );

  // 4. Solicitar cambio de fase
  const requestPhaseTransition = useCallback(
    (targetPhase: InterviewPhase) => {
      setPhase(targetPhase);

      const systemNotice: ChatMessage = {
        id: `turn-sys-${Date.now()}`,
        speaker: "system",
        content: `Transición a fase: ${targetPhase}.`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, systemNotice]);

      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        if (targetPhase !== "INTRO" && targetPhase !== "EVALUATE") {
          const payload: ClientWebSocketMessage = {
            type: "request_phase_transition",
            target_phase: targetPhase,
          };
          socketRef.current.send(JSON.stringify(payload));
        }
      }
    },
    []
  );

  // 5. Enviar evento de integridad
  const sendIntegrityEvent = useCallback(
    (eventType: IntegrityEventType, metadata?: Record<string, unknown>) => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
        const payload: ClientWebSocketMessage = {
          type: "integrity_event",
          event_type: eventType,
          metadata,
          client_timestamp: Date.now(),
        };
        socketRef.current.send(JSON.stringify(payload));
      }
    },
    []
  );

  return {
    phase,
    messages,
    isStreaming,
    connectionStatus,
    timeRemaining,
    testResult,
    isRunningTests,
    sendMessage,
    sendCodeSnapshot,
    runCode,
    requestPhaseTransition,
    sendIntegrityEvent,
  };
}
