from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user, require_organization, require_role
from src.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from src.db.enums import UserRole
from src.db.models import Membership, Organization, User
from src.db.session import get_db
from src.main import app


def test_hash_and_verify_password() -> None:
    hashed = hash_password("correct-horse")
    assert hashed != "correct-horse"
    assert verify_password("correct-horse", hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_and_decode_access_token() -> None:
    user_id = uuid4()
    organization_id = uuid4()
    token = create_access_token(
        user_id=user_id,
        organization_id=organization_id,
        role=UserRole.RECRUITER,
    )
    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["organization_id"] == str(organization_id)
    assert payload["role"] == UserRole.RECRUITER.value
    assert payload["type"] == "access"


def test_expired_and_invalid_tokens() -> None:
    expired = create_access_token(
        user_id=uuid4(),
        organization_id=uuid4(),
        role=UserRole.ADMIN,
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(ValueError, match="invalid token"):
        decode_access_token(expired)
    with pytest.raises(ValueError, match="invalid token"):
        decode_access_token("not-a-jwt")


async def _seed_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    role: UserRole = UserRole.RECRUITER,
    is_active: bool = True,
    with_membership: bool = True,
    organization: Organization | None = None,
) -> tuple[User, Organization | None, Membership | None]:
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    if not with_membership:
        return user, None, None
    org = organization or Organization(name="Org A")
    if organization is None:
        session.add(org)
        await session.flush()
    membership = Membership(user_id=user.id, organization_id=org.id, role=role)
    session.add(membership)
    await session.flush()
    return user, org, membership


async def _login_client(db_session: AsyncSession) -> AsyncClient:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.mark.asyncio
async def test_login_success(db_session: AsyncSession) -> None:
    _user, org, membership = await _seed_user(
        db_session,
        email="recruiter@example.com",
        password="secret123",
        role=UserRole.RECRUITER,
    )
    assert org is not None
    assert membership is not None

    client = await _login_client(db_session)
    try:
        async with client:
            response = await client.post(
                "/auth/login",
                json={"email": "recruiter@example.com", "password": "secret123"},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["role"] == "recruiter"
    assert body["organization_id"] == str(org.id)
    assert body["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(db_session: AsyncSession) -> None:
    await _seed_user(db_session, email="recruiter@example.com", password="secret123")
    client = await _login_client(db_session)
    try:
        async with client:
            response = await client.post(
                "/auth/login",
                json={"email": "recruiter@example.com", "password": "nope"},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(db_session: AsyncSession) -> None:
    await _seed_user(
        db_session,
        email="inactive@example.com",
        password="secret123",
        is_active=False,
    )
    client = await _login_client(db_session)
    try:
        async with client:
            response = await client.post(
                "/auth/login",
                json={"email": "inactive@example.com", "password": "secret123"},
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_current_user_and_tenant_isolation(db_session: AsyncSession) -> None:
    user, org, membership = await _seed_user(
        db_session,
        email="admin@example.com",
        password="secret123",
        role=UserRole.ADMIN,
    )
    assert org is not None
    assert membership is not None
    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    principal = await get_current_user(token=token, session=db_session)
    assert principal.user_id == user.id
    assert principal.organization_id == org.id
    assert principal.role is UserRole.ADMIN

    other_org_id = uuid4()
    with pytest.raises(HTTPException) as forbidden:
        require_organization(other_org_id, principal)
    assert forbidden.value.status_code == 403

    require_organization(org.id, principal)

    recruiter_dep = require_role(UserRole.RECRUITER)
    with pytest.raises(HTTPException) as role_forbidden:
        await recruiter_dep(principal)
    assert role_forbidden.value.status_code == 403

    admin_dep = require_role(UserRole.ADMIN)
    allowed = await admin_dep(principal)
    assert allowed.user_id == user.id
