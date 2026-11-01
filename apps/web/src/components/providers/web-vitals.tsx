"use client";

import { useReportWebVitals } from "next/web-vitals";

export interface WebVitalMetric {
  id: string;
  name: string;
  value: number;
  rating?: "good" | "needs-improvement" | "poor";
}

/**
 * Proveedor de telemetría de Core Web Vitals (LCP, INP, CLS, FCP, TTFB).
 * Captura métricas críticas de rendimiento para auditoría de experiencia de usuario
 * sin interferir en el ciclo de renderizado ni modificar el lazy-loading de Monaco.
 */
export function WebVitals() {
  useReportWebVitals((metric) => {
    // Clasificación estándar de Google Web Vitals para LCP e INP
    let rating: "good" | "needs-improvement" | "poor" = "good";

    if (metric.name === "LCP") {
      // LCP: <= 2500ms bueno, <= 4000ms necesita mejora, > 4000ms deficiente
      rating =
        metric.value <= 2500
          ? "good"
          : metric.value <= 4000
          ? "needs-improvement"
          : "poor";
    } else if (metric.name === "INP") {
      // INP: <= 200ms bueno, <= 500ms necesita mejora, > 500ms deficiente
      rating =
        metric.value <= 200
          ? "good"
          : metric.value <= 500
          ? "needs-improvement"
          : "poor";
    } else if (metric.name === "CLS") {
      // CLS: <= 0.1 bueno, <= 0.25 necesita mejora, > 0.25 deficiente
      rating =
        metric.value <= 0.1
          ? "good"
          : metric.value <= 0.25
          ? "needs-improvement"
          : "poor";
    }

    const report: WebVitalMetric = {
      id: metric.id,
      name: metric.name,
      value: Math.round(metric.value * 100) / 100,
      rating,
    };

    if (process.env.NODE_ENV === "development") {
      // Traza legible en desarrollo para auditoría y benchmarking
      const icon = rating === "good" ? "🟢" : rating === "needs-improvement" ? "🟡" : "🔴";
      console.debug(`[Core-Web-Vitals] ${icon} ${report.name}: ${report.value}ms (${rating})`, report);
    }

    // Exponer a ventana para suites de tests o APM
    if (typeof window !== "undefined") {
      (window as any).__webVitals = (window as any).__webVitals || [];
      (window as any).__webVitals.push(report);
    }
  });

  return null;
}
