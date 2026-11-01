import { test, expect } from "@playwright/test";

test.describe("Flujo Completo de Evaluación Técnica Asistida", () => {
  test("1. Candidato: Acceso con token válido, consentimiento Ley 1581 y sala de entrevista", async ({
    page,
  }) => {
    // 1. Acceder a la sala en vivo con un token de invitación
    await page.goto("/interview/live?token=test_candidate_token_xyz");

    // 2. Esperar pantalla de Consentimiento Informado (Fase INTRO)
    await expect(
      page.getByText("Entrevista Técnica Inicial Asistida por IA")
    ).toBeVisible({ timeout: 15000 });
    await expect(
      page.getByText("Garantía de Equidad (Ley 1581)")
    ).toBeVisible();

    // El botón debe estar deshabilitado hasta aceptar términos
    const startButton = page.getByRole("button", {
      name: /Entiendo las Reglas y Deseo Comenzar/i,
    });
    await expect(startButton).toBeDisabled();

    // 3. Aceptar el consentimiento explícito
    const consentCheckbox = page.locator('input[type="checkbox"]');
    await consentCheckbox.check();
    await expect(startButton).toBeEnabled();

    // 4. Iniciar la entrevista
    await startButton.click();

    // 5. Verificar que ingresamos a la sala dividida (Split-screen)
    await expect(page.getByText("CAND-7F2A")).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText("Conciliación de Pagos PSE y Liquidación Bancaria")
    ).toBeVisible();

    // 6. Validar pestañas del panel izquierdo: "Chat con el Evaluador" y "Enunciado del Problema"
    const chatTab = page.getByRole("button", { name: /Chat con el Evaluador/i });
    const problemTab = page.getByRole("button", { name: /Enunciado del Problema/i });
    await expect(chatTab).toBeVisible();
    await expect(problemTab).toBeVisible();

    // Cambiar al chat y verificar mensaje de bienvenida del agente
    await chatTab.click();
    await expect(
      page.getByText(/¡Hola! Bienvenido a tu entrevista técnica/i)
    ).toBeVisible({ timeout: 10000 });

    // 7. Enviar un mensaje de clarificación en el chat
    const chatInput = page.getByPlaceholder(/Escribe tu pregunta o razonamiento/i);
    await expect(chatInput).toBeVisible();
    await chatInput.fill("¿Podemos asumir que los montos siempre vienen expresados en COP?");
    await chatInput.press("Enter");

    // Verificar que el mensaje del candidato aparece en la conversación
    await expect(
      page.getByText("¿Podemos asumir que los montos siempre vienen expresados en COP?")
    ).toBeVisible();

    // 8. Validar presencia del botón de ejecutar pruebas
    const runTestsButton = page.getByRole("button", {
      name: /Ejecutar Pruebas/i,
    });
    await expect(runTestsButton).toBeVisible();
  });

  test("2. Seguridad de Acceso: Rechazo de token inválido o ausente", async ({
    page,
  }) => {
    // Caso A: Sin token
    await page.goto("/interview/live");
    await expect(
      page.getByText("No se proporcionó ningún token en el enlace.")
    ).toBeVisible({ timeout: 15000 });

    // Caso B: Token inválido
    await page.goto("/interview/live?token=invalid");
    await expect(
      page.getByText("El enlace de evaluación no es válido o ha expirado.")
    ).toBeVisible({ timeout: 15000 });

    const returnButton = page.getByRole("button", { name: /Volver al inicio/i });
    await expect(returnButton).toBeVisible();
  });

  test("3. Demo Interactivo: Ciclo de vida completo, ejecución y reporte defendible", async ({
    page,
  }) => {
    // 1. Acceder al modo demo offline interactivo
    await page.goto("/demo");

    // 2. Verificar que carga el problema demo seleccionado
    await expect(
      page.getByRole("heading", { name: /Conciliación de Pagos PSE/i })
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Entrevistador IA")).toBeVisible();

    // 3. Ejecutar pruebas unitarias en el sandbox simulado
    const runTestsBtn = page.getByRole("button", { name: /Ejecutar Pruebas/i });
    await expect(runTestsBtn).toBeVisible();
    await runTestsBtn.click();

    // Esperar resultado en consola de ejecución
    await expect(
      page.getByText(/3\/3 pruebas superadas exitosamente/i)
    ).toBeVisible({ timeout: 10000 });

    // 4. Finalizar entrevista y generar informe defendible
    const finishBtn = page.getByRole("button", {
      name: /Generar Reporte Defendible/i,
    });
    await expect(finishBtn).toBeVisible();
    await finishBtn.click();

    // 5. Validar pantalla del Reporte Defendible en el demo
    await expect(
      page.getByRole("heading", { name: /Informe Defendible de Evaluación Técnica con IA/i })
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.getByText("CAND-DEMO-7F2A")
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Radar de 5 Dimensiones/i })
    ).toBeVisible();
    await expect(
      page.getByText("Evidencias Forenses Verificables")
    ).toBeVisible();
    await expect(
      page.getByText(/Ley 1581 de 2012/i)
    ).toBeVisible();
  });

  test("4. Reclutador / Evaluador: Vista del informe de resultados con radar de competencias", async ({
    page,
  }) => {
    // Acceder directamente a la página de resultados de una entrevista evaluada
    await page.goto("/interview/results/int-001");

    // Verificar componentes clave del informe
    await expect(
      page.getByRole("heading", { name: /Informe Defendible de Evaluación Técnica/i })
    ).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("CAND-7F2A")).toBeVisible();
    await expect(page.getByText("Puntuación General")).toBeVisible();
    await expect(page.getByText("de 5.0")).toBeVisible();
    await expect(page.getByText(/Desempeño Sobresaliente/i)).toBeVisible();
    await expect(page.getByText(/RECOMENDACIÓN: CONTRATAR/i)).toBeVisible();

    // Verificar radar de competencias y rúbrica
    await expect(page.getByText("Radar de Competencias")).toBeVisible();
    await expect(page.getByRole("button", { name: /Resolución de Problemas/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Calidad de Código/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Diseño y Arquitectura/i })).toBeVisible();
    await expect(page.getByText("Evidencias Auditables Vinculadas")).toBeVisible();
  });
});
