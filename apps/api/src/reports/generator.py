"""Generador de informes defendibles en PDF usando Jinja2 y WeasyPrint."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jinja2
import weasyprint  # type: ignore[import-untyped]

from src.api.schemas.evaluation import EvaluationReport


class ReportPdfGenerator:
    """Generador de informes técnicos en formato PDF con auditoría SHA-256."""

    def __init__(self) -> None:
        templates_dir = Path(__file__).parent / "templates"
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(templates_dir),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        self._template = self._env.get_template("report.html")

    def _get_dimensions(self, report: EvaluationReport) -> list[dict[str, Any]]:
        """Extrae dimensiones tanto si report tiene dimensions como si tiene competencies."""
        report_dims = getattr(report, "dimensions", None)
        if report_dims:
            return [
                {
                    "dimension": getattr(d, "dimension", getattr(d, "name", str(d))),
                    "score": float(getattr(d, "score", 0)),
                    "reasoning": getattr(d, "reasoning", "") or "",
                }
                for d in report_dims
            ]
        dims: list[dict[str, Any]] = []
        competencies = getattr(report, "competencies", {}) or {}
        for name, score in competencies.items():
            dims.append({
                "dimension": name,
                "score": float(score),
                "reasoning": f"Puntaje obtenido: {score}/5 según la rúbrica.",
            })
        return dims

    def generate_radar_svg(self, dimensions: list[dict[str, Any]]) -> str:
        """Genera un gráfico de radar vectorial SVG para las dimensiones evaluadas."""
        if not dimensions:
            return ""

        width = 300
        height = 250
        cx = 150
        cy = 125
        radius = 85
        n = len(dimensions)

        # 1. Anillos / polígonos concéntricos de la grilla (niveles 1 a 5)
        grid_lines = []
        for level in range(1, 6):
            r = radius * (level / 5)
            points = []
            for i in range(n):
                angle = -math.pi / 2 + i * (2 * math.pi / n)
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                points.append(f"{x:.1f},{y:.1f}")
            grid_lines.append(f'<polygon points="{" ".join(points)}" fill="none" stroke="#e2e8f0" stroke-width="1"/>')

        # 2. Ejes radiales y etiquetas
        axis_elements = []
        score_points = []
        for i, dim in enumerate(dimensions):
            angle = -math.pi / 2 + i * (2 * math.pi / n)
            x_end = cx + radius * math.cos(angle)
            y_end = cy + radius * math.sin(angle)
            axis_elements.append(f'<line x1="{cx}" y1="{cy}" x2="{x_end:.1f}" y2="{y_end:.1f}" stroke="#cbd5e1" stroke-width="1"/>')

            label_r = radius + 20
            lx = cx + label_r * math.cos(angle)
            ly = cy + label_r * math.sin(angle)
            name = dim.get("dimension", "").replace("_", " ").title()
            score = dim.get("score", 0)

            anchor = "middle"
            if math.cos(angle) > 0.3:
                anchor = "start"
            elif math.cos(angle) < -0.3:
                anchor = "end"
            axis_elements.append(
                f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-family="-apple-system, sans-serif" font-size="7.5" fill="#475569">{name} ({score:.1f})</text>'
            )

            # Vértice de puntuación
            s = min(5.0, max(0.0, float(score)))
            sr = radius * (s / 5.0)
            sx = cx + sr * math.cos(angle)
            sy = cy + sr * math.sin(angle)
            score_points.append(f"{sx:.1f},{sy:.1f}")

        polygon_str = " ".join(score_points)
        score_polygon = f'<polygon points="{polygon_str}" fill="#0284c7" fill-opacity="0.25" stroke="#0284c7" stroke-width="2"/>'
        dots = [f'<circle cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="3" fill="#0369a1"/>' for p in score_points]

        return (
            f'<svg viewBox="0 0 {width} {height}" width="300" height="250" xmlns="http://www.w3.org/2000/svg">'
            + "".join(grid_lines)
            + "".join(axis_elements)
            + score_polygon
            + "".join(dots)
            + "</svg>"
        )

    def _calculate_audit_hash(self, report: EvaluationReport, final_code: str) -> str:
        """Calcular un hash criptográfico determinista SHA-256 del contenido evaluado."""
        dimensions = self._get_dimensions(report)
        payload = {
            "masked_candidate_id": report.masked_candidate_id,
            "overall_score": float(report.overall_score),
            "recommendation": report.recommendation,
            "dimensions": dimensions,
            "evidence": [
                {"quote": e.evidence_quote, "turn_id": e.turn_id} for e in report.evidence
            ],
            "code_hash": hashlib.sha256(final_code.encode("utf-8")).hexdigest(),
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def generate_pdf(
        self,
        report: EvaluationReport,
        vacancy_title: str = "Desarrollador de Software",
        final_code: str = "",
        code_language: str = "python",
        model_used: str = "grok-beta / evaluator-v2",
    ) -> tuple[bytes, str]:
        """Generar el PDF binario del informe defendible.

        Retorna una tupla: (bytes_del_pdf, audit_hash_sha256).
        """
        audit_hash = self._calculate_audit_hash(report, final_code)
        dimensions = self._get_dimensions(report)
        radar_svg = self.generate_radar_svg(dimensions)
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        rendered_html = self._template.render(
            report=report,
            dimensions=dimensions,
            radar_svg=radar_svg,
            vacancy_title=vacancy_title,
            final_code=final_code,
            code_language=code_language,
            audit_hash=audit_hash,
            generated_at=now_str,
            model_used=model_used,
        )

        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
        return pdf_bytes, audit_hash
