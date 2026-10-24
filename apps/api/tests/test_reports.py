"""Tests for Defensible PDF Report Generator (WeasyPrint) and /interviews/{id}/report.pdf.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.schemas.evaluation import EvaluationEvidence, EvaluationReport
from src.core.security import create_access_token, hash_password
from src.db.enums import InterviewPhase, InterviewStatus, Seniority, UserRole
from src.db.models import Interview, Membership, Organization, Snapshot, User, Vacancy
from src.main import app
from src.reports.generator import ReportPdfGenerator


def test_pdf_generator_unit():
    generator = ReportPdfGenerator()
    report = EvaluationReport(
        id=str(uuid4()),
        masked_candidate_id="CAND-TEST",
        overall_score=4.2,
        recommendation="hire",
        needs_human_review=False,
        discrepancy_note=None,
        competencies={
            "problem_solving": 4,
            "algorithmic_reasoning": 5,
            "code_quality": 4,
            "technical_communication": 4,
            "complexity_management": 4,
        },
        evidence=[
            EvaluationEvidence(
                competency="algorithmic_reasoning",
                score=5,
                evidence_quote="Usó sliding window reduciendo la complejidad a O(N)",
                turn_id="turn-1",
                reasoning="Identificó la optimización óptima de tiempo de ejecución.",
            )
        ],
        strengths=["Dominio de estructuras de datos", "Claridad al comunicar su enfoque"],
        risks=[],
        suggested_human_questions=["¿Cómo escalarías esto a nivel distribuido?"],
        evaluated_at=datetime.now(UTC),
    )

    pdf_bytes, audit_hash = generator.generate_pdf(
        report=report,
        vacancy_title="Ingeniero Backend Senior",
        final_code="def solve(arr):\n    return sum(arr)",
        code_language="python",
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(audit_hash) == 64  # SHA-256


@pytest.mark.asyncio
async def test_get_report_pdf_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/interviews/{uuid4()}/report.pdf")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_report_pdf_nonexistent(db_session):
    org = Organization(name="Report Org")
    db_session.add(org)
    await db_session.flush()

    user = User(
        email="report_admin@test.com",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    auth_headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/interviews/{uuid4()}/report.pdf",
            headers=auth_headers,
        )
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_report_pdf_success(db_session):
    org = Organization(name="Report Success Org")
    db_session.add(org)
    await db_session.flush()

    user = User(
        email="report_user@test.com",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    db_session.add(membership)
    await db_session.flush()

    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    auth_headers = {"Authorization": f"Bearer {token}"}

    vacancy = Vacancy(
        organization_id=org.id,
        title="Senior Python Architect",
        role_category="Backend",
        seniority=Seniority.SENIOR,
        raw_description="Diseño de arquitecturas escalables",
        profile={"required_skills": ["Python", "FastAPI"]},
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_email="candidate.pdf@test.com",
        candidate_name="Candidato Reporte",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
        status=InterviewStatus.COMPLETED,
        phase=InterviewPhase.EVALUATE,
    )
    db_session.add(interview)
    await db_session.flush()

    snapshot = Snapshot(
        interview_id=interview.id,
        code="def hello(): return 'world'",
        language="python",
        phase="CODING",
        reason="run",
    )
    db_session.add(snapshot)

    from src.db.models.interview import Evaluation, EvaluationDimension

    evaluation = Evaluation(
        interview_id=interview.id,
        overall_score=4.0,
        recommendation="hire",
        needs_human_review=False,
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(evaluation)
    await db_session.flush()

    for dim in [
        "problem_solving",
        "algorithmic_reasoning",
        "code_quality",
        "technical_communication",
        "complexity_management",
    ]:
        db_session.add(
            EvaluationDimension(
                evaluation_id=evaluation.id,
                name=dim,
                score=4,
                reasoning=f"Excelente desempeño en {dim}",
            )
        )
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/interviews/{interview.id}/report.pdf",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "x-audit-hash-sha256" in response.headers
        assert len(response.headers["x-audit-hash-sha256"]) == 64
        assert response.content.startswith(b"%PDF-")
