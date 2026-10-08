/**
 * Contrato de Mensajería WebSocket para la Sala de Entrevista en Tiempo Real.
 * Utilizado por Next.js (Cristian) y FastAPI (Samuel) a través de @evaluador/contracts.
 */

export type InterviewPhase =
  | "INTRO"
  | "PROBLEM"
  | "CLARIFY"
  | "DESIGN"
  | "CODING"
  | "PROBE"
  | "WRAPUP"
  | "EVALUATE";

export type CodeLanguage = "python" | "javascript" | "sql";

export type SnapshotReason = "debounce" | "run" | "blur" | "phase_transition";

export type IntegrityEventType =
  | "blur"
  | "focus"
  | "paste"
  | "paste_large"
  | "tab_switch";

export type ExecutionStatus =
  | "success"
  | "test_failure"
  | "compile_error"
  | "timeout"
  | "runtime_error";

// ============================================================================
// Mensajes que el Cliente (Cristian) envía al Servidor (Samuel)
// ============================================================================

export type ClientChatMessage = {
  type: "chat_message";
  content: string;
  client_timestamp: number;
};

export type ClientCodeSnapshotMessage = {
  type: "code_snapshot";
  code: string;
  language: CodeLanguage;
  reason: SnapshotReason;
  cursor_line?: number;
  cursor_column?: number;
  client_timestamp: number;
};

export type ClientRunCodeMessage = {
  type: "run_code";
  code: string;
  language: CodeLanguage;
};

export type ClientRequestPhaseTransitionMessage = {
  type: "request_phase_transition";
  target_phase: Exclude<InterviewPhase, "INTRO" | "EVALUATE">;
  reason?: string;
};

export type ClientIntegrityEventMessage = {
  type: "integrity_event";
  event_type: IntegrityEventType;
  metadata?: {
    pasted_length?: number;
    time_away_ms?: number;
    [key: string]: unknown;
  };
  client_timestamp: number;
};

export type ClientPingMessage = {
  type: "ping";
  client_timestamp: number;
};

export type ClientWebSocketMessage =
  | ClientChatMessage
  | ClientCodeSnapshotMessage
  | ClientRunCodeMessage
  | ClientRequestPhaseTransitionMessage
  | ClientIntegrityEventMessage
  | ClientPingMessage;

// ============================================================================
// Mensajes que el Servidor (Samuel) envía al Cliente (Cristian)
// ============================================================================

export type ServerAgentTokenMessage = {
  type: "agent_token";
  turn_id: string;
  delta: string;
};

export type ServerAgentTurnCompleteMessage = {
  type: "agent_turn_complete";
  turn_id: string;
  full_content: string;
  suggested_transition?: InterviewPhase;
};

export type ServerPhaseChangedMessage = {
  type: "phase_changed";
  current_phase: InterviewPhase;
  available_transitions: InterviewPhase[];
  phase_instructions?: string;
};

export type ServerCodeExecutionResultMessage = {
  type: "code_execution_result";
  status: ExecutionStatus;
  stdout: string;
  stderr: string;
  execution_time_ms: number;
  tests_passed: number;
  total_tests: number;
  test_details?: Array<{
    test_name: string;
    passed: boolean;
    message?: string;
  }>;
};

export type ServerSessionTickMessage = {
  type: "session_tick";
  time_remaining_seconds: number;
  current_phase: InterviewPhase;
};

export type ServerErrorMessage = {
  type: "error";
  code: string;
  message: string;
  recoverable: boolean;
};

export type ServerPongMessage = {
  type: "pong";
  client_timestamp: number;
  server_timestamp: number;
};

export type ServerWebSocketMessage =
  | ServerAgentTokenMessage
  | ServerAgentTurnCompleteMessage
  | ServerPhaseChangedMessage
  | ServerCodeExecutionResultMessage
  | ServerSessionTickMessage
  | ServerErrorMessage
  | ServerPongMessage;

// Unión de todos los mensajes posibles en el protocolo
export type WebSocketMessage = ClientWebSocketMessage | ServerWebSocketMessage;
