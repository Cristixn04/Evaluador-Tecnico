"""Generador de informes defendibles en PDF usando Jinja2 y WeasyPrint."""

from __future__ import annotations

import hashlib
import json
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
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        rendered_html = self._template.render(
            report=report,
            dimensions=dimensions,
            vacancy_title=vacancy_title,
            final_code=final_code,
            code_language=code_language,
            audit_hash=audit_hash,
            generated_at=now_str,
            model_used=model_used,
        )

        pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
        return pdf_bytes, audit_hash
