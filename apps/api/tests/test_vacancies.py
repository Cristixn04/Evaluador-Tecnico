import json
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.db.enums import Seniority, UserRole
from src.db.models import Membership, Organization, User, Vacancy
from src.db.session import get_db
from src.llm.exceptions import LLMTimeoutError
from src.llm.factory import get_llm_client
from src.llm.types import ChatCompletion, ChatMessage, TokenUsage
from src.main import app

VALID_PROFILE = {
    "role_category": "backend",
    "seniority": "mid",
    "required_skills": ["python", "fastapi"],
    "preferred_skills": ["postgresql"],
    "primary_language": "python",
    "focus_areas": ["apis"],
}

DESCRIPTION = "Buscamos backend Python con FastAPI. PostgreSQL es deseable."


class FakeLLM:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> ChatCompletion:
        if self.error is not None:
            raise self.error
        assert self.content is not None
        return ChatCompletion(content=self.content, model="grok-4.6", usage=TokenUsage())


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


async def _client(db_session: AsyncSession, llm: FakeLLM) -> AsyncClient:
    async def override_get_db():
        yield db_session

    async def override_llm():
        yield llm

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm_client] = override_llm
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


def _auth_header(user: User, org: Organization) -> dict[str, str]:
    token = create_access_token(user_id=user.id, organization_id=org.id, role=UserRole.RECRUITER)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_vacancy_requires_auth(db_session: AsyncSession) -> None:
    client = await _client(db_session, FakeLLM(json.dumps(VALID_PROFILE)))
    try:
        async with client:
            response = await client.post(
                "/vacancies",
                json={"title": "Backend", "raw_description": DESCRIPTION},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_vacancy_persists_profile(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter@example.com", org_name="Org A")
    client = await _client(db_session, FakeLLM(json.dumps(VALID_PROFILE)))
    try:
        async with client:
            response = await client.post(
                "/vacancies",
                headers=_auth_header(user, org),
                json={"title": "Backend Python", "raw_description": DESCRIPTION},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Backend Python"
    assert body["role_category"] == "backend"
    assert body["seniority"] == "mid"
    assert body["profile"]["primary_language"] == "python"
    stored = await db_session.get(Vacancy, UUID(body["id"]))
    assert stored is not None
    assert stored.organization_id == org.id
    assert stored.seniority is Seniority.MID


@pytest.mark.asyncio
async def test_create_vacancy_rejects_empty_description(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter@example.com", org_name="Org A")
    client = await _client(db_session, FakeLLM(json.dumps(VALID_PROFILE)))
    try:
        async with client:
            response = await client.post(
                "/vacancies",
                headers=_auth_header(user, org),
                json={"title": "Backend", "raw_description": "   "},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_vacancy_malformed_llm_response(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter@example.com", org_name="Org A")
    client = await _client(db_session, FakeLLM("not-json"))
    try:
        async with client:
            response = await client.post(
                "/vacancies",
                headers=_auth_header(user, org),
                json={"title": "Backend", "raw_description": DESCRIPTION},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 502


@pytest.mark.asyncio
async def test_create_vacancy_llm_timeout(db_session: AsyncSession) -> None:
    user, org = await _seed_member(db_session, email="recruiter@example.com", org_name="Org A")
    client = await _client(db_session, FakeLLM(error=LLMTimeoutError("LLM request timed out")))
    try:
        async with client:
            response = await client.post(
                "/vacancies",
                headers=_auth_header(user, org),
                json={"title": "Backend", "raw_description": DESCRIPTION},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 504


@pytest.mark.asyncio
async def test_get_profile_and_tenant_isolation(db_session: AsyncSession) -> None:
    owner, org_a = await _seed_member(db_session, email="a@example.com", org_name="Org A")
    stranger, org_b = await _seed_member(db_session, email="b@example.com", org_name="Org B")
    vacancy = Vacancy(
        organization_id=org_a.id,
        title="Backend",
        raw_description=DESCRIPTION,
        role_category="backend",
        seniority=Seniority.MID,
        profile={
            "required_skills": ["python"],
            "preferred_skills": [],
            "primary_language": "python",
            "focus_areas": ["apis"],
        },
    )
    db_session.add(vacancy)
    await db_session.flush()

    client = await _client(db_session, FakeLLM(json.dumps(VALID_PROFILE)))
    try:
        async with client:
            own = await client.get(
                f"/vacancies/{vacancy.id}/profile",
                headers=_auth_header(owner, org_a),
            )
            other = await client.get(
                f"/vacancies/{vacancy.id}/profile",
                headers=_auth_header(stranger, org_b),
            )
    finally:
        app.dependency_overrides.clear()
    assert own.status_code == 200
    assert own.json()["primary_language"] == "python"
    assert other.status_code == 404
