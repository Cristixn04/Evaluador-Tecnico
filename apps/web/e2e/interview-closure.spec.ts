import { test, expect } from "@playwright/test";

test.describe("Cierre formal de entrevista técnica (E2E Browser Test)", () => {
  test("debe ejecutar el flujo completo: WRAPUP -> abrir modal -> cancelar -> reabrir -> confirmar -> EVALUATE", async ({
    page,
  }) => {
    // 1. Abrir aplicación en sala de entrevista con token rehidratado en fase WRAPUP
    await page.goto("/interview/live?token=tok_wrapup_candidate");
    await page.waitForLoadState("domcontentloaded");

    // 2. Verificar que la sala cargó y que el botón de entrega formal es visible en WRAPUP
    const finishBtn = page.locator("#finish-interview-btn");
    await expect(finishBtn).toBeVisible({ timeout: 15000 });
    await expect(finishBtn).toContainText("Entregar y Finalizar Entrevista");

    // 3. Abrir modal de confirmación
    await finishBtn.click();

    // 4. Verificar presencia del modal accesible con rol dialog y advertencia
    const modal = page.locator("#closure-modal");
    await expect(modal).toBeVisible();
    await expect(modal).toHaveAttribute("role", "dialog");
    await expect(modal).toHaveAttribute("aria-modal", "true");
    await expect(modal.locator("#closure-modal-title")).toContainText("¿Confirmas la entrega definitiva?");

    // 5. Cancelar en el modal y verificar que permanece en WRAPUP sin transicionar
    const cancelBtn = page.locator("#cancel-closure-btn");
    await expect(cancelBtn).toBeVisible();
    await cancelBtn.click();

    // Verificar que el modal se cerró y el botón de entrega sigue disponible
    await expect(modal).not.toBeVisible();
    await expect(finishBtn).toBeVisible();

    // 6. Volver a abrir el modal
    await finishBtn.click();
    await expect(modal).toBeVisible();

    // 7. Confirmar entrega definitiva
    const confirmBtn = page.locator("#confirm-closure-btn");
    await expect(confirmBtn).toBeVisible();
    await confirmBtn.click();

    // 8. Verificar transición a EVALUATE y renderizado de la pantalla final
    const finalHeading = page.locator("h2:has-text('Entrevista Finalizada'), h3:has-text('Entrevista Finalizada')");
    await expect(finalHeading).toBeVisible({ timeout: 10000 });

    const finalDescription = page.locator("text=Has completado y entregado formalmente tu sesión de evaluación técnica");
    await expect(finalDescription).toBeVisible();

    // 9. Verificar que el botón de entrega ya NO está disponible en la pantalla final
    await expect(finishBtn).not.toBeVisible();
  });
});
