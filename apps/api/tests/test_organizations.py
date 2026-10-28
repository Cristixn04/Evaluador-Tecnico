import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.interview import InterviewSummary
from src.core.security import create_access_token, hash_password
from src.db.enums import InterviewPhase, InterviewStatus, UserRole
from src.db.models import Membership, Organization, User, Vacancy
from src.db.models.interview import Evaluation, Interview
from src.main import app


async def _seed_member(
    session: AsyncSession,
    *,
    email: str,
    org_name: str,
    role: UserRole = UserRole.RECRUITER,
) -> tuple[User, Organization]:
    org = Organization(name=org_name)
    user = User(email=email.lower(), hashed_password=hash_password("secret123"), is_active=True)
    session.add_all([org, user])
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=org.id, role=role))
    await session.flush()
    return user, org


def _auth_header(user: User, org: Organization, role: UserRole = UserRole.RECRUITER) -> dict[str, str]:
    token = create_access_token(user_id=user.id, organization_id=org.id, role=role)
    return {"Authorization": f"Bearer {token}"}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_list_interviews_as_recruiter_success(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_a@example.com", org_name="Org A")
    vacancy = Vacancy(
        organization_id=org.id,
        title="Senior Python Backend",
        raw_description="Python vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name="Alice Smith",
        candidate_email="alice@example.com",
        access_token="secret-access-token-123",
        status=InterviewStatus.IN_PROGRESS,
        phase=InterviewPhase.CODING,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    db_session.add(interview)
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == str(interview.id)
    assert data[0]["masked_candidate_id"] == f"CAND-{interview.id.hex[:4].upper()}"
    assert data[0]["vacancy_title"] == "Senior Python Backend"
    assert data[0]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_list_interviews_forbidden_for_other_org(db_session: AsyncSession) -> None:
    user_a, org_a = await _seed_member(db_session, email="recruiter_a2@example.com", org_name="Org A2")
    _user_b, org_b = await _seed_member(db_session, email="recruiter_b@example.com", org_name="Org B")
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org_b.id}/interviews",
            headers=_auth_header(user_a, org_a),
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Organization mismatch"


@pytest.mark.asyncio
async def test_list_interviews_unauthenticated(db_session: AsyncSession) -> None:
    _user, org = await _seed_member(db_session, email="recruiter_unauth@example.com", org_name="Org Unauth")
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(f"/organizations/{org.id}/interviews")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_interviews_nonexistent_organization(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_nonexistent@example.com", org_name="Org Exist")
    await db_session.commit()

    non_existent_id = uuid.uuid4()
    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{non_existent_id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


@pytest.mark.asyncio
async def test_list_interviews_invalid_uuid_slug(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_mock@example.com", org_name="Org Mock")
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            "/organizations/org-colombia-tech/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Organization not found"


@pytest.mark.asyncio
async def test_list_interviews_without_evaluation(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_noeval@example.com", org_name="Org NoEval")
    vacancy = Vacancy(
        organization_id=org.id,
        title="DevOps Engineer",
        raw_description="DevOps vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name="Bob Jones",
        candidate_email="bob@example.com",
        access_token="tok-devops-001",
        status=InterviewStatus.PENDING,
        phase=InterviewPhase.INTRO,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(interview)
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["overall_score"] is None
    assert data[0]["recommendation"] is None
    assert data[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_interviews_with_evaluation(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_eval@example.com", org_name="Org Eval")
    vacancy = Vacancy(
        organization_id=org.id,
        title="Lead Architect",
        raw_description="Architect vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name="Carol Danvers",
        candidate_email="carol@example.com",
        access_token="tok-arch-002",
        status=InterviewStatus.EVALUATED,
        phase=InterviewPhase.EVALUATE,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(interview)
    await db_session.flush()

    evaluation = Evaluation(
        interview_id=interview.id,
        overall_score=4.5,
        recommendation="hire",
        needs_human_review=False,
        evaluated_at=datetime.now(UTC),
    )
    db_session.add(evaluation)
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["overall_score"] == 4.5
    assert data[0]["recommendation"] == "hire"
    assert data[0]["status"] == "evaluated"


@pytest.mark.asyncio
async def test_list_interviews_no_pii_leakage(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_pii@example.com", org_name="Org PII")
    vacancy = Vacancy(
        organization_id=org.id,
        title="Fullstack Developer",
        raw_description="Fullstack vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name="Secret Candidate Name",
        candidate_email="very_confidential@domain.com",
        access_token="super-secret-token-xyz",
        status=InterviewStatus.IN_PROGRESS,
        phase=InterviewPhase.CODING,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(interview)
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    raw_text = response.text
    # Verify confidential data is nowhere in the serialized JSON text
    assert "Secret Candidate Name" not in raw_text
    assert "very_confidential@domain.com" not in raw_text
    assert "candidate_name" not in raw_text
    assert "candidate_email" not in raw_text


@pytest.mark.asyncio
async def test_list_interviews_no_token_secrets_leakage(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_tok@example.com", org_name="Org Tokens")
    vacancy = Vacancy(
        organization_id=org.id,
        title="Security Analyst",
        raw_description="Security vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    interview = Interview(
        vacancy_id=vacancy.id,
        candidate_name="David Doe",
        candidate_email="david@example.com",
        access_token="my-special-token-9999",
        status=InterviewStatus.IN_PROGRESS,
        phase=InterviewPhase.CODING,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(interview)
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    raw_text = response.text
    assert "my-special-token-9999" not in raw_text
    assert "access_token" not in raw_text
    assert "ws_token" not in raw_text


@pytest.mark.asyncio
async def test_list_interviews_conforms_to_interview_summary_and_sorted(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_sort@example.com", org_name="Org Sort")
    vacancy = Vacancy(
        organization_id=org.id,
        title="Backend Engineer",
        raw_description="Backend vacancy",
    )
    db_session.add(vacancy)
    await db_session.flush()

    now = datetime.now(UTC)
    int1 = Interview(
        vacancy_id=vacancy.id,
        candidate_name="Old Candidate",
        candidate_email="old@example.com",
        status=InterviewStatus.PENDING,
        phase=InterviewPhase.INTRO,
        created_at=now - timedelta(hours=2),
        expires_at=now + timedelta(days=1),
    )
    int2 = Interview(
        vacancy_id=vacancy.id,
        candidate_name="New Candidate",
        candidate_email="new@example.com",
        status=InterviewStatus.IN_PROGRESS,
        phase=InterviewPhase.CODING,
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    db_session.add_all([int1, int2])
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Verify each item can be validated strictly as InterviewSummary
    summary_new = InterviewSummary.model_validate(data[0])
    summary_old = InterviewSummary.model_validate(data[1])

    # Verify descending sort order by created_at
    assert summary_new.id == str(int2.id)
    assert summary_old.id == str(int1.id)
    assert summary_new.created_at >= summary_old.created_at


@pytest.mark.asyncio
async def test_list_interviews_empty_org(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter_empty@example.com", org_name="Org Empty")
    await db_session.commit()

    client = _client()
    async with client:
        response = await client.get(
            f"/organizations/{org.id}/interviews",
            headers=_auth_header(user, org),
        )

    assert response.status_code == 200
    assert response.json() == []
