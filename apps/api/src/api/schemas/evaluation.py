from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvaluationDimension(BaseModel):
    """Una dimensión de la rúbrica (1-5)."""
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Identificador de la dimensión en snake_case")
    score: int = Field(..., ge=1, le=5, description="Puntuación de 1 a 5")
    reasoning: str | None = Field(None, description="Justificación de la puntuación")

    @field_validator("score")
    @classmethod
    def validate_score_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("Score must be between 1 and 5")
        return v


class EvaluationEvidence(BaseModel):
    """Evidencia citada para una dimensión."""
    model_config = ConfigDict(from_attributes=True)

    competency: str = Field(..., description="Nombre de la competencia/habilidad")
    score: int = Field(..., ge=1, le=5, description="Puntuación de 1 a 5")
    evidence_quote: str = Field(..., description="Cita o fragmento de evidencia")
    turn_id: str = Field(..., description="ID del turno de conversación")
    reasoning: str | None = Field(None, description="Razonamiento de la evidencia")


class EvaluationReport(BaseModel):
    """Schema alineado con el contrato OpenAPI EvaluationReport."""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="ID de la evaluación")
    masked_candidate_id: str = Field(..., description="ID anonimizado del candidato")
    overall_score: float = Field(..., ge=0, le=5, description="Media aritmética simple de 5 dimensiones")
    recommendation: Literal["hire", "borderline", "reject"] = Field(
        ..., description="Recomendación orientativa"
    )
    needs_human_review: bool = Field(
        ..., description="Si requiere revisión humana"
    )
    discrepancy_note: str | None = Field(None, description="Nota de discrepancia")
    strengths: list[str] = Field(default_factory=list, description="Puntos fuertes")
    risks: list[str] = Field(default_factory=list, description="Riesgos identificados")
    suggested_human_questions: list[str] = Field(
        default_factory=list, description="Preguntas sugerentes para revisión humana"
    )
    competencies: dict[str, int] = Field(
        default_factory=dict,
        description="Diccionario {dimension_name: score}"
    )
    evidence: list[EvaluationEvidence] = Field(
        default_factory=list, description="Evidencias citadas"
    )
    created_at: datetime = Field(
        default_factory=datetime.now, description="Fecha de creación"
    )
    evaluated_at: datetime = Field(
        default_factory=datetime.now, description="Fecha de evaluación"
    )


class EvaluationCreate(BaseModel):
    """Datos de entrada para crear una evaluación."""
    interview_id: str = Field(..., description="ID de la entrevista evaluada")
    overall_score: float = Field(..., ge=0, le=5, description="Media aritmética simple")
    recommendation: Literal["hire", "borderline", "reject"] = Field(
        ..., description="Recomendación orientativa"
    )
    needs_human_review: bool = Field(
        ..., description="Si requiere revisión humana"
    )
    discrepancy_note: str | None = Field(None, description="Nota de discrepancia")
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggested_human_questions: list[str] = Field(default_factory=list)
    competencies: dict[str, int] = Field(
        default_factory=dict,
        description="Diccionario {dimension_name: score}"
    )
    evidence: list[EvaluationEvidence] = Field(
        default_factory=list, description="Evidencias citadas"
    )
