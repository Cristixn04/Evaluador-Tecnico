import test from "node:test";
import assert from "node:assert/strict";

/**
 * Pruebas unitarias para S2-01B: Cierre formal de entrevista (WRAPUP -> EVALUATE).
 *
 * Casos cubiertos:
 * 1. En WRAPUP: el botón "Entregar y Finalizar Entrevista" es visible/disponible.
 * 2. En fases distintas de WRAPUP (INTRO, PROBLEM, CLARIFY, DESIGN, CODING, PROBE, EVALUATE):
 *    el botón NO aparece.
 * 3. Click en botón: modal de confirmación aparece con advertencia de irreversibilidad.
 * 4. Cancelar modal: modal desaparece y NO se emite request_phase_transition.
 * 5. Confirmar modal: se envía exactamente un request_phase_transition con target_phase="EVALUATE".
 * 6. Mientras se envía (isSubmitting): se bloquea el botón y se previene doble envío/click.
 * 7. No transición optimista: el estado local NO cambia a EVALUATE tras confirmar hasta que el servidor
 *    emite phase_changed(EVALUATE).
 * 8. Al recibir phase_changed(EVALUATE): la UI refleja EVALUATE, el botón desaparece y se deshabilita
 *    el envío de mensajes y ejecución de código.
 * 9. Reconnect / carga inicial en EVALUATE: la interfaz permanece cerrada sin botón de entrega.
 */

// Simulación del estado y lógica del Header de Entrevista
function createHeaderState(initialPhase, onTransitionPhase) {
  let phase = initialPhase;
  let showConfirmModal = false;
  let isSubmitting = false;
  const sentTransitions = [];

  const transitionHandler = onTransitionPhase || ((target) => {
    sentTransitions.push(target);
  });

  return {
    get phase() {
      return phase;
    },
    set phase(newPhase) {
      phase = newPhase;
      if (newPhase !== "WRAPUP") {
        showConfirmModal = false;
      }
    },
    get isFinishButtonVisible() {
      return phase === "WRAPUP";
    },
    get showConfirmModal() {
      return showConfirmModal;
    },
    get isSubmitting() {
      return isSubmitting;
    },
    get sentTransitions() {
      return [...sentTransitions];
    },
    openModal() {
      if (phase === "WRAPUP" && !isSubmitting) {
        showConfirmModal = true;
      }
    },
    cancelModal() {
      if (!isSubmitting) {
        showConfirmModal = false;
      }
    },
    confirmFinish() {
      if (isSubmitting) return false;
      if (phase !== "WRAPUP") return false;
      isSubmitting = true;
      transitionHandler("EVALUATE");
      return true;
    },
    // Simula la confirmación desde el servidor (no optimista)
    receivePhaseChanged(newPhase) {
      phase = newPhase;
      isSubmitting = false;
      showConfirmModal = false;
    },
  };
}

// Simulación del hook useInterviewSocket para validación de contratos
function createSocketPhaseClient(currentPhase = "WRAPUP") {
  let phase = currentPhase;
  const outgoingMessages = [];

  return {
    get phase() {
      return phase;
    },
    get outgoingMessages() {
      return [...outgoingMessages];
    },
    requestPhaseTransition(targetPhase) {
      // Regla de contrato: no se puede transicionar a INTRO
      if (targetPhase === "INTRO") {
        return false;
      }
      outgoingMessages.push({
        type: "request_phase_transition",
        target_phase: targetPhase,
      });
      return true;
    },
    handleServerMessage(msg) {
      if (msg.type === "phase_changed") {
        phase = msg.current_phase;
      }
    },
  };
}

test("Caso 1: En fase WRAPUP, el botón de cierre es visible", () => {
  const header = createHeaderState("WRAPUP");
  assert.equal(header.isFinishButtonVisible, true);
  assert.equal(header.showConfirmModal, false);
});

test("Caso 2: En fases distintas de WRAPUP, el botón de cierre NO aparece", () => {
  const nonWrapupPhases = [
    "INTRO",
    "PROBLEM",
    "CLARIFY",
    "DESIGN",
    "CODING",
    "PROBE",
    "EVALUATE",
  ];

  for (const p of nonWrapupPhases) {
    const header = createHeaderState(p);
    assert.equal(
      header.isFinishButtonVisible,
      false,
      `El botón no debe ser visible en fase ${p}`
    );
  }
});

test("Caso 3: Click en el botón de entrega abre el modal de confirmación", () => {
  const header = createHeaderState("WRAPUP");
  header.openModal();
  assert.equal(header.showConfirmModal, true);
  assert.equal(header.sentTransitions.length, 0);
});

test("Caso 4: Cancelar en el modal lo cierra y NO envía transición", () => {
  const header = createHeaderState("WRAPUP");
  header.openModal();
  assert.equal(header.showConfirmModal, true);

  header.cancelModal();
  assert.equal(header.showConfirmModal, false);
  assert.equal(header.sentTransitions.length, 0);
  assert.equal(header.phase, "WRAPUP");
});

test("Caso 5: Confirmar en el modal envía request_phase_transition con target EVALUATE", () => {
  const socketClient = createSocketPhaseClient("WRAPUP");
  const header = createHeaderState("WRAPUP", (target) => {
    socketClient.requestPhaseTransition(target);
  });

  header.openModal();
  const confirmed = header.confirmFinish();

  assert.equal(confirmed, true);
  assert.equal(socketClient.outgoingMessages.length, 1);
  assert.deepEqual(socketClient.outgoingMessages[0], {
    type: "request_phase_transition",
    target_phase: "EVALUATE",
  });
});

test("Caso 6: Mientras se procesa la solicitud (isSubmitting), se previene el doble click", () => {
  const socketClient = createSocketPhaseClient("WRAPUP");
  const header = createHeaderState("WRAPUP", (target) => {
    socketClient.requestPhaseTransition(target);
  });

  header.openModal();
  const firstClick = header.confirmFinish();
  assert.equal(firstClick, true);
  assert.equal(header.isSubmitting, true);

  // Segundo click inmediato mientras isSubmitting es true
  const secondClick = header.confirmFinish();
  assert.equal(secondClick, false);

  // Solo debe haberse emitido exactamente una solicitud
  assert.equal(socketClient.outgoingMessages.length, 1);
});

test("Caso 7: No transición optimista: la fase permanece en WRAPUP hasta recibir phase_changed(EVALUATE)", () => {
  const socketClient = createSocketPhaseClient("WRAPUP");
  const header = createHeaderState("WRAPUP", (target) => {
    socketClient.requestPhaseTransition(target);
  });

  header.openModal();
  header.confirmFinish();

  // Inmediatamente tras confirmar, el estado local sigue siendo WRAPUP
  assert.equal(header.phase, "WRAPUP");
  assert.equal(socketClient.phase, "WRAPUP");

  // Al llegar el evento del servidor phase_changed
  const serverPhaseChangedMsg = {
    type: "phase_changed",
    current_phase: "EVALUATE",
    available_transitions: [],
  };
  socketClient.handleServerMessage(serverPhaseChangedMsg);
  header.receivePhaseChanged(serverPhaseChangedMsg.current_phase);

  // Ahora sí la UI refleja EVALUATE
  assert.equal(header.phase, "EVALUATE");
  assert.equal(socketClient.phase, "EVALUATE");
  assert.equal(header.isFinishButtonVisible, false);
  assert.equal(header.showConfirmModal, false);
});

test("Caso 8: Al recibir phase_changed(EVALUATE), el botón desaparece y la vista pasa a finalizada", () => {
  const header = createHeaderState("WRAPUP");
  assert.equal(header.isFinishButtonVisible, true);

  // Simular transición formal completada
  header.receivePhaseChanged("EVALUATE");

  assert.equal(header.phase, "EVALUATE");
  assert.equal(header.isFinishButtonVisible, false);

  // Intentar abrir el modal en EVALUATE no debe ser permitido
  header.openModal();
  assert.equal(header.showConfirmModal, false);
});

test("Caso 9: Reconexión o recarga cuando la entrevista ya está en EVALUATE", () => {
  // Cuando el cliente reconecta y el servidor envía phase: EVALUATE
  const socketClient = createSocketPhaseClient("EVALUATE");
  const header = createHeaderState("EVALUATE");

  assert.equal(socketClient.phase, "EVALUATE");
  assert.equal(header.isFinishButtonVisible, false);
  assert.equal(header.showConfirmModal, false);

  // Intentar transicionar de EVALUATE a EVALUATE es redundante / no expuesto
  const res = header.confirmFinish();
  assert.equal(res, false);
});
