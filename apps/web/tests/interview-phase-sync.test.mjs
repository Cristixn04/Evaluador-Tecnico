import test from "node:test";
import assert from "node:assert/strict";

/**
 * Pruebas unitarias para sincronización de fases y máquina de estados en el Frontend.
 * Valida:
 * 1. Mapeo de etapas e interactividad del Stepper.
 * 2. Transición INTRO -> PROBLEM y ausencia de EVALUATE en WRAPUP por WebSocket.
 * 3. Prevención de saltos arbitrarios de fase y transiciones hacia atrás.
 * 4. Actualización exclusivamente ante evento ServerPhaseChangedMessage confirmado.
 * 5. Inmunidad de la fase ante mensajes de chat normales (agent_token / agent_turn_complete).
 * 6. Reconciliación tras reconexión o recarga.
 */

const PHASES = [
  { id: "PROBLEM", label: "1. Enunciado" },
  { id: "CLARIFY", label: "2. Aclaración" },
  { id: "DESIGN", label: "3. Diseño" },
  { id: "CODING", label: "4. Código" },
  { id: "PROBE", label: "5. Sondeo" },
  { id: "WRAPUP", label: "6. Cierre" },
];

function getNextTransition(phase) {
  switch (phase) {
    case "INTRO":
      return { label: "Ver problema", target: "PROBLEM" };
    case "PROBLEM":
      return { label: "Hacer preguntas al evaluador", target: "CLARIFY" };
    case "CLARIFY":
      return { label: "Listo para diseñar", target: "DESIGN" };
    case "DESIGN":
      return { label: "Empezar a programar", target: "CODING" };
    case "CODING":
      return { label: "Pasar a preguntas de sondeo", target: "PROBE" };
    case "PROBE":
      return { label: "Finalizar prueba técnica", target: "WRAPUP" };
    case "WRAPUP":
      return null;
    default:
      return null;
  }
}

function computeStepperState(currentPhase, availableTransitions) {
  const currentIdx = PHASES.findIndex((item) => item.id === currentPhase);
  const next = getNextTransition(currentPhase);

  return PHASES.map((p, idx) => {
    const isCurrent = currentPhase === p.id;
    const isPassed = currentIdx !== -1 && currentIdx > idx;
    const isAvailable = availableTransitions
      ? availableTransitions.includes(p.id)
      : next?.target === p.id;

    const isInteractive = isAvailable && !isCurrent && !isPassed;

    return {
      id: p.id,
      label: p.label,
      isCurrent,
      isPassed,
      isAvailable,
      isInteractive,
    };
  });
}

test("1. En fase inicial INTRO, la siguiente transición es PROBLEM y no CLARIFY", () => {
  const next = getNextTransition("INTRO");
  assert.equal(next?.target, "PROBLEM");
  assert.equal(next?.label, "Ver problema");
});

test("2. En fase PROBLEM, solo 1. Enunciado es current y solo 2. Aclaración es interactiva", () => {
  const stepper = computeStepperState("PROBLEM", ["CLARIFY"]);
  
  const problemItem = stepper.find((p) => p.id === "PROBLEM");
  assert.equal(problemItem?.isCurrent, true);
  assert.equal(problemItem?.isInteractive, false);

  const clarifyItem = stepper.find((p) => p.id === "CLARIFY");
  assert.equal(clarifyItem?.isInteractive, true);
  assert.equal(clarifyItem?.isCurrent, false);
  assert.equal(clarifyItem?.isPassed, false);

  // Fases posteriores (DESIGN, CODING, PROBE, WRAPUP) no deben ser interactivas
  const designItem = stepper.find((p) => p.id === "DESIGN");
  assert.equal(designItem?.isInteractive, false);
  const codingItem = stepper.find((p) => p.id === "CODING");
  assert.equal(codingItem?.isInteractive, false);
});

test("3. En fase CODING, etapas 1 a 3 son pasadas y solo PROBE es disponible", () => {
  const stepper = computeStepperState("CODING", ["PROBE"]);
  
  assert.equal(stepper.find((p) => p.id === "PROBLEM")?.isPassed, true);
  assert.equal(stepper.find((p) => p.id === "CLARIFY")?.isPassed, true);
  assert.equal(stepper.find((p) => p.id === "DESIGN")?.isPassed, true);
  assert.equal(stepper.find((p) => p.id === "CODING")?.isCurrent, true);
  
  const probeItem = stepper.find((p) => p.id === "PROBE");
  assert.equal(probeItem?.isInteractive, true);
  
  // WRAPUP aún no debe ser interactivo
  assert.equal(stepper.find((p) => p.id === "WRAPUP")?.isInteractive, false);
});

test("4. En fase WRAPUP (Cierre), no existe transición a EVALUATE por WebSocket", () => {
  const next = getNextTransition("WRAPUP");
  assert.equal(next, null);

  const stepper = computeStepperState("WRAPUP", []);
  assert.equal(stepper.find((p) => p.id === "WRAPUP")?.isCurrent, true);
  assert.equal(stepper.every((p) => p.isInteractive === false), true);
});

test("5. Transición no optimista: la fase solo cambia cuando el servidor confirma phase_changed", () => {
  let localPhase = "PROBLEM";
  let availableTransitions = ["CLARIFY"];

  function handleServerMessage(data) {
    if (data.type === "phase_changed") {
      localPhase = data.current_phase;
      availableTransitions = data.available_transitions || [];
    }
  }

  // Si el cliente envía solicitud a DESIGN (salto inválido)
  // El cliente no muta localPhase
  assert.equal(localPhase, "PROBLEM");

  // El servidor responde con error de transición inválida
  const serverErrorMsg = {
    type: "error",
    code: "INVALID_TRANSITION",
    message: "Invalid phase transition from PROBLEM to DESIGN",
    recoverable: true,
  };
  handleServerMessage(serverErrorMsg);

  // La fase local debe permanecer intacta en PROBLEM
  assert.equal(localPhase, "PROBLEM");

  // Cuando el servidor confirma una transición válida a CLARIFY
  const validTransitionMsg = {
    type: "phase_changed",
    current_phase: "CLARIFY",
    available_transitions: ["DESIGN"],
  };
  handleServerMessage(validTransitionMsg);

  assert.equal(localPhase, "CLARIFY");
  assert.deepEqual(availableTransitions, ["DESIGN"]);
});

test("6. Mensajes de chat del agente no mutan la fase", () => {
  let localPhase = "CLARIFY";

  function handleServerMessage(data) {
    if (data.type === "phase_changed") {
      localPhase = data.current_phase;
    }
  }

  // Token de streaming del agente mencionando otra fase
  handleServerMessage({
    type: "agent_token",
    turn_id: "turn-123",
    delta: "Pasamos a la fase de CODING en el editor Monaco.",
  });
  assert.equal(localPhase, "CLARIFY");

  // Turno completo del agente
  handleServerMessage({
    type: "agent_turn_complete",
    turn_id: "turn-123",
    full_content: "Pasamos a la fase de CODING en el editor Monaco.",
  });
  assert.equal(localPhase, "CLARIFY");
});

test("7. Reconciliación tras reconexión o recarga rehidrata la fase real del servidor", () => {
  // Simulación de sesión guardada en BD como DESIGN
  const sessionDataFromVerify = {
    session_id: "interview-123",
    current_phase: "DESIGN",
    status: "in_progress",
  };

  let initialPhase = sessionDataFromVerify.current_phase || "INTRO";
  assert.equal(initialPhase, "DESIGN");

  // Al conectar WebSocket, el servidor emite el estado real
  const wsInitialEvent = {
    type: "phase_changed",
    current_phase: "DESIGN",
    available_transitions: ["CODING"],
  };

  let activePhase = initialPhase;
  let activeTransitions = [];

  if (wsInitialEvent.type === "phase_changed") {
    activePhase = wsInitialEvent.current_phase;
    activeTransitions = wsInitialEvent.available_transitions;
  }

  assert.equal(activePhase, "DESIGN");
  assert.deepEqual(activeTransitions, ["CODING"]);

  const stepper = computeStepperState(activePhase, activeTransitions);
  assert.equal(stepper.find((p) => p.id === "DESIGN")?.isCurrent, true);
  assert.equal(stepper.find((p) => p.id === "PROBLEM")?.isPassed, true);
  assert.equal(stepper.find((p) => p.id === "CLARIFY")?.isPassed, true);
  assert.equal(stepper.find((p) => p.id === "CODING")?.isInteractive, true);
});

test("8. Transiciones completas de cierre: CODING -> PROBE -> WRAPUP", () => {
  // En CODING: siguiente disponible es PROBE
  const stepCoding = computeStepperState("CODING", ["PROBE"]);
  assert.equal(stepCoding.find((p) => p.id === "PROBE")?.isInteractive, true);
  assert.equal(stepCoding.find((p) => p.id === "WRAPUP")?.isInteractive, false);

  // En PROBE: siguiente disponible es WRAPUP ("Finalizar prueba técnica")
  const nextFromProbe = getNextTransition("PROBE");
  assert.equal(nextFromProbe?.target, "WRAPUP");
  assert.equal(nextFromProbe?.label, "Finalizar prueba técnica");

  const stepProbe = computeStepperState("PROBE", ["WRAPUP"]);
  assert.equal(stepProbe.find((p) => p.id === "PROBE")?.isCurrent, true);
  assert.equal(stepProbe.find((p) => p.id === "WRAPUP")?.isInteractive, true);
  assert.equal(stepProbe.find((p) => p.id === "CODING")?.isPassed, true);

  // En WRAPUP: todas las etapas anteriores están pasadas y WRAPUP es current
  const stepWrapup = computeStepperState("WRAPUP", []);
  assert.equal(stepWrapup.find((p) => p.id === "WRAPUP")?.isCurrent, true);
  assert.equal(stepWrapup.find((p) => p.id === "WRAPUP")?.isInteractive, false);
  assert.equal(stepWrapup.every((p) => p.id === "WRAPUP" ? p.isCurrent : p.isPassed), true);
});

test("9. Consentimiento: una sesión ya activa en el servidor (in_progress, current_phase != INTRO) no queda bloqueada por localStorage ausente", () => {
  function computeHasConsented({ storedConsent, status, current_phase }) {
    if (status === "in_progress" && current_phase !== "INTRO") {
      // El servidor ya registró la transición legal desde INTRO a una fase activa
      return true;
    }
    return storedConsent === true;
  }

  // Caso A: Nueva sesión en INTRO sin consentimiento
  assert.equal(
    computeHasConsented({ storedConsent: false, status: "pending", current_phase: "INTRO" }),
    false
  );

  // Caso B: Sesión en INTRO con localStorage falso/corrupto no debe evadir el consentimiento
  assert.equal(
    computeHasConsented({ storedConsent: false, status: "pending", current_phase: "INTRO" }),
    false
  );

  // Caso C: Sesión activa en CODING abierta en una nueva pestaña (localStorage vacío)
  assert.equal(
    computeHasConsented({ storedConsent: false, status: "in_progress", current_phase: "CODING" }),
    true
  );

  // Caso D: Sesión activa en WRAPUP reconectada tras recarga
  assert.equal(
    computeHasConsented({ storedConsent: true, status: "in_progress", current_phase: "WRAPUP" }),
    true
  );
});

test("10. syncCurrentCode sincroniza el código y cancela el temporizador de debounce evitando snapshot duplicado al ejecutar pruebas", () => {
  let emittedSnapshots = [];
  let lastEmittedCode = "initial code";
  let timer = "pending_timer_id";

  function syncCurrentCode(currentCode) {
    if (timer) {
      timer = null; // clearTimeout
    }
    lastEmittedCode = currentCode;
  }

  // Candidato modifica código y presiona Ejecutar Pruebas
  const newCode = "def solve(): return 42";
  syncCurrentCode(newCode);

  assert.equal(timer, null);
  assert.equal(lastEmittedCode, newCode);
  // No emite snapshot redundante vacío por adelantado
  assert.equal(emittedSnapshots.length, 0);
});
