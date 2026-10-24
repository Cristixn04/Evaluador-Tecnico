"""Integration tests for invitation link contract, verification, and isolation.

These tests run against an isolated test database (evaluador_test_db) to ensure
that evaluador_db (used for E2E) is never truncated or modified.
"""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.security import create_access_token, hash_password
from src.db.base import Base
from src.db.enums import Seniority, UserRole
from src.db.models import Interview, Invitation, Organization, Problem, User, Vacancy
from src.db.models.auth import Membership
from src.db.session import get_db
from src.main import app

TEST_DB_URL = "postgresql+asyncpg://evaluador:evaluador_password_dev@localhost:5435/evaluador_test_db"


@pytest.fixture
async def test_db_engine():
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    async with engine.connect() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.commit()
    yield engine
    await engine.dispose()


@pytest.fixture
async def isolated_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        # Clean isolated test db tables
        await session.execute(
            text(
                "TRUNCATE TABLE organizations, users, memberships, vacancies, problems, "
                "interviews, turns, snapshots, invitations, evaluations, "
                "evaluation_dimensions, evaluation_evidence RESTART IDENTITY CASCADE;"
            )
        )
        await session.commit()
        yield session


@pytest.fixture
async def app_client(isolated_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield isolated_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def setup_org_and_vacancy(isolated_session: AsyncSession):
    # Org A
    org_a = Organization(id=uuid.uuid4(), name="Tech Colombia Org A")
    isolated_session.add(org_a)
    await isolated_session.flush()

    user_a = User(
        id=uuid.uuid4(),
        email="recruiter_a@tech.co",
        hashed_password=hash_password("RecruiterPass123!"),
        is_active=True,
    )
    isolated_session.add(user_a)
    await isolated_session.flush()

    membership_a = Membership(
        id=uuid.uuid4(),
        user_id=user_a.id,
        organization_id=org_a.id,
        role="admin",
    )
    isolated_session.add(membership_a)

    vacancy_a = Vacancy(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        title="Backend Engineer Python",
        raw_description="Looking for Python backend engineers.",
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python", "cache"],
            "preferred_skills": ["redis"],
            "primary_language": "python",
            "focus_areas": [],
        },
    )
    isolated_session.add(vacancy_a)

    # Org B (for multi-tenant isolation testing)
    org_b = Organization(id=uuid.uuid4(), name="Tech Colombia Org B")
    isolated_session.add(org_b)
    await isolated_session.flush()

    user_b = User(
        id=uuid.uuid4(),
        email="recruiter_b@tech.co",
        hashed_password=hash_password("RecruiterPass123!"),
        is_active=True,
    )
    isolated_session.add(user_b)
    await isolated_session.flush()

    membership_b = Membership(
        id=uuid.uuid4(),
        user_id=user_b.id,
        organization_id=org_b.id,
        role="admin",
    )
    isolated_session.add(membership_b)

    # Seed problem
    problem = Problem(
        id=uuid.uuid4(),
        title="Cache Invalidation Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Implement an LRU cache with TTL.",
        tags=["python", "cache"],
    )
    isolated_session.add(problem)

    await isolated_session.commit()

    token_a = create_access_token(
        user_id=user_a.id,
        organization_id=org_a.id,
        role=UserRole.ADMIN,
        expires_delta=timedelta(hours=1),
    )
    token_b = create_access_token(
        user_id=user_b.id,
        organization_id=org_b.id,
        role=UserRole.ADMIN,
        expires_delta=timedelta(hours=1),
    )

    return {
        "org_a": org_a,
        "vacancy_a": vacancy_a,
        "token_a": token_a,
        "org_b": org_b,
        "token_b": token_b,
        "problem": problem,
    }


@pytest.mark.asyncio
async def test_invitation_creation_contract_and_security(
    app_client: AsyncClient,
    isolated_session: AsyncSession,
    setup_org_and_vacancy: dict,
):
    """Test that invitation creation returns a valid URL pointing to /interview/live?token=...

    and that plaintext tokens are NEVER persisted in PostgreSQL.
    """
    vacancy = setup_org_and_vacancy["vacancy_a"]
    token_a = setup_org_and_vacancy["token_a"]

    # 1. Create invitation via recruiter API
    resp = await app_client.post(
        f"/vacancies/{vacancy.id}/invitations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "candidate_name": "Candidato Contrato",
            "candidate_email": "candidato.contrato@test.co",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()

    # Verify response schema
    assert "invitation_id" in data
    assert "access_token" in data
    assert "access_url" in data
    assert "masked_candidate_id" in data
    assert "expires_at" in data

    access_token = data["access_token"]
    access_url = data["access_url"]

    # Verify link points to /interview/live with the token query param
    assert access_url == f"/interview/live?token={access_token}"
    assert data["masked_candidate_id"].startswith("CAND-")

    # 2. Check persistence in DB: token_hash is bcrypt, plaintext NOT saved
    inv_id = uuid.UUID(data["invitation_id"])
    result = await isolated_session.execute(select(Invitation).where(Invitation.id == inv_id))
    inv_db = result.scalar_one()

    assert inv_db.candidate_name == "Candidato Contrato"
    assert inv_db.candidate_email == "candidato.contrato@test.co"
    assert inv_db.token_selector == access_token[:16]
    assert inv_db.token_hash.startswith("$2b$")  # bcrypt hash
    assert access_token not in inv_db.token_hash  # Plaintext token NOT stored
    assert inv_db.used_at is None
    assert inv_db.interview_id is None


@pytest.mark.asyncio
async def test_session_verify_bearer_and_query_token_idempotent(
    app_client: AsyncClient,
    isolated_session: AsyncSession,
    setup_org_and_vacancy: dict,
):
    """Test verification via Bearer header and via query param, ensuring idempotency."""
    vacancy = setup_org_and_vacancy["vacancy_a"]
    token_a = setup_org_and_vacancy["token_a"]

    # Create invitation
    inv_resp = await app_client.post(
        f"/vacancies/{vacancy.id}/invitations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "candidate_name": "Candidato Idempotente",
            "candidate_email": "candidato.idem@test.co",
        },
    )
    assert inv_resp.status_code == 201
    candidate_token = inv_resp.json()["access_token"]

    # 1. Verify with Bearer header
    v1_resp = await app_client.get(
        "/sessions/verify",
        headers={"Authorization": f"Bearer {candidate_token}"},
    )
    assert v1_resp.status_code == 200, v1_resp.text
    session_1 = v1_resp.json()
    assert "session_id" in session_1
    assert "ws_token" in session_1
    assert "ws_url" in session_1
    assert session_1["problem"]["title"] == "Cache Invalidation Problem"

    session_id_1 = session_1["session_id"]

    # 2. Verify with query param ?token= (same invitation token)
    v2_resp = await app_client.get(f"/sessions/verify?token={candidate_token}")
    assert v2_resp.status_code == 200, v2_resp.text
    session_2 = v2_resp.json()

    # Idempotent: must return the EXACT same session ID
    assert session_2["session_id"] == session_id_1

    # Check database: only 1 interview record created
    result = await isolated_session.execute(
        select(Interview).where(Interview.vacancy_id == vacancy.id)
    )
    interviews = list(result.scalars().all())
    assert len(interviews) == 1
    assert str(interviews[0].id) == session_id_1


@pytest.mark.asyncio
async def test_session_verify_rejection_invalid_missing_expired(
    app_client: AsyncClient,
    isolated_session: AsyncSession,
    setup_org_and_vacancy: dict,
):
    """Test that missing, altered, and expired tokens are rejected with HTTP 401."""
    # 1. Missing token
    resp_missing = await app_client.get("/sessions/verify")
    assert resp_missing.status_code == 401
    assert resp_missing.json()["detail"] == "Invalid or missing token"

    # 2. Altered / invalid token
    resp_invalid = await app_client.get(
        "/sessions/verify",
        headers={"Authorization": "Bearer completely-invalid-token-12345"},
    )
    assert resp_invalid.status_code == 401
    assert resp_invalid.json()["detail"] == "Invalid or expired token"

    # 3. Altered token with matching selector but bad body
    vacancy = setup_org_and_vacancy["vacancy_a"]
    token_a = setup_org_and_vacancy["token_a"]
    inv_resp = await app_client.post(
        f"/vacancies/{vacancy.id}/invitations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "candidate_name": "Candidato Alterado",
            "candidate_email": "candidato.alterado@test.co",
        },
    )
    real_token = inv_resp.json()["access_token"]
    tampered_token = real_token[:16] + "tampered_suffix_value_here"

    resp_tampered = await app_client.get(
        "/sessions/verify",
        headers={"Authorization": f"Bearer {tampered_token}"},
    )
    assert resp_tampered.status_code == 401
    assert resp_tampered.json()["detail"] == "Invalid or expired token"

    # 4. Expired invitation
    inv_id = uuid.UUID(inv_resp.json()["invitation_id"])
    invitation = await isolated_session.get(Invitation, inv_id)
    assert invitation is not None
    invitation.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await isolated_session.commit()

    resp_expired = await app_client.get(
        "/sessions/verify",
        headers={"Authorization": f"Bearer {real_token}"},
    )
    assert resp_expired.status_code == 401
    assert resp_expired.json()["detail"] == "Invalid or expired token"

    # 5. Already used invitation (used_at set)
    invitation.expires_at = datetime.now(UTC) + timedelta(days=1)
    invitation.used_at = datetime.now(UTC)
    await isolated_session.commit()

    resp_used = await app_client.get(
        "/sessions/verify",
        headers={"Authorization": f"Bearer {real_token}"},
    )
    assert resp_used.status_code == 401
    assert resp_used.json()["detail"] == "Invalid or expired token"


@pytest.mark.asyncio
async def test_ws_token_validation_and_lifecycle(
    app_client: AsyncClient,
    setup_org_and_vacancy: dict,
):
    """Test that ws_token returned by /sessions/verify is valid, ephemeral, and revocable."""
    from src.core.ws_tokens import WSTokenRevokedError, ws_token_service

    vacancy = setup_org_and_vacancy["vacancy_a"]
    token_a = setup_org_and_vacancy["token_a"]

    # 1. Create invitation
    inv_resp = await app_client.post(
        f"/vacancies/{vacancy.id}/invitations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "candidate_name": "Candidato WS",
            "candidate_email": "candidato.ws@test.co",
        },
    )
    assert inv_resp.status_code == 201
    candidate_token = inv_resp.json()["access_token"]

    # 2. Verify candidate session
    verify_resp = await app_client.get(f"/sessions/verify?token={candidate_token}")
    assert verify_resp.status_code == 200
    session_data = verify_resp.json()
    ws_token = session_data["ws_token"]
    session_id = uuid.UUID(session_data["session_id"])

    # 3. Validate WS token via service
    validated_session_id = await ws_token_service.validate_ws_token(ws_token)
    assert validated_session_id == session_id

    # 4. Revoke token and verify revocation error
    await ws_token_service.revoke_ws_token(ws_token)
    with pytest.raises(WSTokenRevokedError):
        await ws_token_service.validate_ws_token(ws_token)


@pytest.mark.asyncio
async def test_multi_tenant_isolation_on_invitations(
    app_client: AsyncClient,
    setup_org_and_vacancy: dict,
):
    """Ensure recruiter from Org B cannot invite for Org A's vacancy."""
    vacancy_a = setup_org_and_vacancy["vacancy_a"]
    token_b = setup_org_and_vacancy["token_b"]

    resp = await app_client.post(
        f"/vacancies/{vacancy_a.id}/invitations",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "candidate_name": "Candidato Espía",
            "candidate_email": "espia@competidor.co",
        },
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Vacancy not found"

