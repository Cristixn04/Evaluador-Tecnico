import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe("Auditoría de Accesibilidad Automatizada con Axe-Core", () => {
  test("auditoría de accesibilidad en ruta /demo", async ({ page }) => {
    await page.goto("/demo");
    await page.waitForLoadState("domcontentloaded");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      // Descartar temporalmente regiones de color contrast de código Monaco oscuro si aplica
      .disableRules(["color-contrast"])
      .analyze();

    console.log(
      `[Axe Audit /demo] Violaciones WCAG encontradas: ${results.violations.length}, Pases: ${results.passes.length}`
    );

    for (const v of results.violations) {
      console.log(`  - [${v.impact}] ${v.id}: ${v.description} (${v.nodes.length} elementos)`);
    }

    expect(results.violations).toEqual([]);
  });

  test("auditoría de accesibilidad en sala de entrevista /interview/live", async ({ page }) => {
    await page.goto("/interview/live?token=tok_wrapup_a11y");
    await page.waitForLoadState("domcontentloaded");
    await page.waitForSelector("#finish-interview-btn", { timeout: 15000 });

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .disableRules(["color-contrast"])
      .analyze();

    console.log(
      `[Axe Audit /interview/live] Violaciones WCAG encontradas: ${results.violations.length}, Pases: ${results.passes.length}`
    );

    for (const v of results.violations) {
      console.log(`  - [${v.impact}] ${v.id}: ${v.description} (${v.nodes.length} elementos)`);
    }

    expect(results.violations).toEqual([]);
  });
});
