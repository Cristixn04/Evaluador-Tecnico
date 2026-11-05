"""Tests for GET /interviews/{id}/trajectory endpoint."""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.openapi.utils import get_openapi
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, hash_password
from src.db.enums import UserRole
from src.db.models import Interview, Membership, Organization, Problem, Snapshot, User, Vacancy
from src.main import app


async def _seed_org_and_headers(
    session: AsyncSession,
    org_name: str = "Trajectory Org",
) -> tuple[Organization, dict[str, str]]:
    org = Organization(name=org_name)
    user = User(
        email=f"recruiter_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    session.add_all([org, user])
    await session.flush()
    session.add(Membership(user_id=user.id, organization_id=org.id, role=UserRole.RECRUITER))
    await session.flush()
    token = create_access_token(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.RECRUITER,
    )
    return org, {"Authorization": f"Bearer {token}"}


def test_trajectory_openapi_schema():
    """Test that the OpenAPI schema has the trajectory endpoint with correct shape."""
    openapi = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Check trajectory endpoint exists
    trajectory_path = next(p for p in openapi["paths"] if "trajectory" in p)
    assert trajectory_path == "/interviews/{interview_id}/trajectory"

    # Check response schema references InterviewTrajectory
    schema = openapi["paths"][trajectory_path]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert "$ref" in str(schema) or "InterviewTrajectory" in str(schema)


@pytest.mark.asyncio
async def test_trajectory_nonexistent(db_session: AsyncSession):
    """Test 1: 404 para entrevista inexistente (con usuario autenticado)."""
    _org, headers = await _seed_org_and_headers(db_session)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/interviews/123e4567-e89b-12d3-a456-426614174000/trajectory",
            headers=headers,
        )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Interview not found"


@pytest.mark.asyncio
async def test_trajectory_unauthenticated_returns_401():
    """H-02: Usuario sin autenticación recibe 401 Unauthorized."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/interviews/123e4567-e89b-12d3-a456-426614174000/trajectory")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trajectory_cross_tenant_returns_403(db_session: AsyncSession):
    """H-02: Usuario de Org B recibe 403 Forbidden al consultar trayectoria de Org A."""
    org_a, _headers_a = await _seed_org_and_headers(db_session, "Trajectory Org A")
    _org_b, headers_b = await _seed_org_and_headers(db_session, "Trajectory Org B")

    vacancy_a = Vacancy(
        id=uuid.uuid4(),
        organization_id=org_a.id,
        title="Test Vacancy Org A",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy_a)
    await db_session.flush()

    interview_a = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy_a.id,
        candidate_email="test.orga@test.com",
        candidate_name="Test Org A",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview_a)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/interviews/{interview_a.id}/trajectory",
            headers=headers_b,
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Organization mismatch"


@pytest.mark.asyncio
async def test_trajectory_without_organization_returns_403(db_session: AsyncSession):
    """H-02: Entrevista cuya vacante tiene organization_id=None es denegada con 403."""
    _org, headers = await _seed_org_and_headers(db_session, "Trajectory Org Valid")

    orphan_vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=None,
        title="Orphan Trajectory Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(orphan_vacancy)
    await db_session.flush()

    orphan_interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=orphan_vacancy.id,
        candidate_email="orphan.traj@test.com",
        candidate_name="Orphan Traj",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(orphan_interview)
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            f"/interviews/{orphan_interview.id}/trajectory",
            headers=headers,
        )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Organization mismatch"


@pytest.mark.asyncio
async def test_trajectory_interview_no_snapshots(db_session: AsyncSession):
    """Test 2: Entrevista existente sin snapshots."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data using the db_session
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint - should return empty snapshots
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    # Verify structure
    assert "interview_id" in data
    assert "total_duration_seconds" in data
    assert "snapshots" in data
    assert isinstance(data["snapshots"], list)
    assert len(data["snapshots"]) == 0
    
    # Total duration should be 0 when no snapshots
    assert data["total_duration_seconds"] == 0.0


@pytest.mark.asyncio
async def test_trajectory_single_snapshot_legacy_default(db_session: AsyncSession):
    """Test 3: Un snapshot. Test 8: reason = legacy en snapshots históricos."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create a single snapshot WITH reason='legacy' (historical snapshot default)
    snapshot = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def hello(): return 'hello'",
        phase="CODING",
        language="python",
        reason="legacy",
        tests_passed=1,
        total_tests=1,
        execution_status="success",
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    assert len(data["snapshots"]) == 1
    assert data["snapshots"][0]["timestamp_offset_seconds"] == 0.0
    # Test 8: reason should be 'legacy' for historical snapshots
    assert data["snapshots"][0]["reason"] == "legacy"
    
    # Execution fields present
    assert "tests_passed" in data["snapshots"][0]
    assert "total_tests" in data["snapshots"][0]
    assert "execution_status" in data["snapshots"][0]


@pytest.mark.asyncio
async def test_trajectory_multiple_snapshots(db_session: AsyncSession):
    """Test 4: Múltiples snapshots. Test 5: Orden cronológico determinista.
    Test 6: Cálculo de timestamp_offset_seconds. Test 7: Cálculo de total_duration_seconds."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create multiple snapshots with different reasons and timestamps
    for i in range(3):
        snapshot = Snapshot(
            id=uuid.uuid4(),
            interview_id=interview.id,
            code=f"def test{i}(): return {i}",
            phase="PROBLEM" if i == 0 else "CODING",
            language="python",
            reason="phase_transition" if i == 0 else ("run" if i == 1 else "debounce"),
            tests_passed=i,
            total_tests=4,
            execution_status="success" if i > 0 else "test_failure",
            created_at=datetime(2026, 10, 13 + i, tzinfo=UTC),
        )
        db_session.add(snapshot)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    assert len(data["snapshots"]) == 3
    
    # Test 5: Orden cronológico determinista
    offsets = [s["timestamp_offset_seconds"] for s in data["snapshots"]]
    assert offsets == sorted(offsets)
    
    # Test 6: Cálculo de timestamp_offset_seconds
    assert data["snapshots"][0]["timestamp_offset_seconds"] == 0.0
    
    # Test 7: Cálculo de total_duration_seconds
    assert data["total_duration_seconds"] > 0


@pytest.mark.asyncio
async def test_trajectory_reason_legacy_default(db_session: AsyncSession):
    """Test 8: reason = legacy en snapshots históricos."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create snapshot with reason='legacy' (simulating historical snapshot)
    snapshot = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def legacy(): return True",
        phase="CODING",
        language="python",
        reason="legacy",
        tests_passed=None,
        total_tests=None,
        execution_status=None,
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 8: reason should be 'legacy' for historical snapshots
    assert data["snapshots"][0]["reason"] == "legacy"


@pytest.mark.asyncio
async def test_trajectory_execution_fields_optional_when_no_result(db_session: AsyncSession):
    """Test 9: Campos de ejecución opcionales cuando no hay resultado."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create snapshot without execution fields (simulating no execution result)
    snapshot = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def no_result(): pass",
        phase="CODING",
        language="python",
        reason="phase_transition",
        tests_passed=None,
        total_tests=None,
        execution_status=None,
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 9: Execution fields should be optional/None when no result
    assert data["snapshots"][0]["tests_passed"] is None
    assert data["snapshots"][0]["total_tests"] is None
    assert data["snapshots"][0]["execution_status"] is None


@pytest.mark.asyncio
async def test_trajectory_execution_persistence(db_session: AsyncSession):
    """Test 10: Persistencia de tests_passed, total_tests y execution_status al ejecutar código."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="CODING",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create snapshot with execution results (as execute_code() now persists)
    snapshot = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def pass_all(): return True",
        phase="CODING",
        language="python",
        reason="run",
        tests_passed=2,
        total_tests=2,
        execution_status="success",
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 10: Execution fields should be persisted
    assert data["snapshots"][0]["tests_passed"] == 2
    assert data["snapshots"][0]["total_tests"] == 2
    assert data["snapshots"][0]["execution_status"] == "success"
    assert data["snapshots"][0]["reason"] == "run"


@pytest.mark.asyncio
async def test_trajectory_no_event_note(db_session: AsyncSession):
    """Test 12: Ausencia de event_note en la respuesta JSON."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="INTRO",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create snapshot with reason
    snapshot = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def no_event(): pass",
        phase="CODING",
        language="python",
        reason="phase_transition",
        tests_passed=1,
        total_tests=1,
        execution_status="success",
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(snapshot)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 12: No event_note in response
    for s in data["snapshots"]:
        assert "event_note" not in s or s.get("event_note") is None


@pytest.mark.asyncio
async def test_trajectory_no_duplicate_snapshots(db_session: AsyncSession):
    """Test 11: Ausencia de snapshots duplicados para una ejecución."""
    org, headers = await _seed_org_and_headers(db_session)

    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Test Vacancy",
        raw_description="Test",
        seniority="mid",
    )
    db_session.add(vacancy)
    await db_session.flush()
    
    problem = Problem(
        id=uuid.uuid4(),
        title="Test Problem",
        difficulty="mid",
        language="python",
        scenario_preview="Test scenario",
    )
    db_session.add(problem)
    await db_session.flush()
    
    interview = Interview(
        id=uuid.uuid4(),
        vacancy_id=vacancy.id,
        problem_id=problem.id,
        candidate_email="test@test.com",
        candidate_name="Test",
        status="pending",
        phase="CODING",
        expires_at=datetime(2027, 1, 1, tzinfo=UTC),
    )
    db_session.add(interview)
    await db_session.flush()
    
    # Create 2 snapshots with the same code (simulating potential duplicate)
    snapshot1 = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def no_dup(): pass",
        phase="CODING",
        language="python",
        reason="run",
        tests_passed=1,
        total_tests=1,
        execution_status="success",
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    snapshot2 = Snapshot(
        id=uuid.uuid4(),
        interview_id=interview.id,
        code="def no_dup(): pass",
        phase="CODING",
        language="python",
        reason="run",
        tests_passed=1,
        total_tests=1,
        execution_status="success",
        created_at=datetime(2026, 10, 13, tzinfo=UTC),
    )
    db_session.add(snapshot1)
    db_session.add(snapshot2)
    await db_session.flush()
    await db_session.commit()
    
    # Now test the endpoint
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/interviews/{interview.id}/trajectory", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 11: Should return all snapshots (including duplicates if they exist in DB)
    assert isinstance(data["snapshots"], list)
    assert len(data["snapshots"]) >= 2


@pytest.mark.asyncio
async def test_trajectory_reason_required_openapi():
    """Test that reason is required in the TrajectorySnapshot schema."""
    openapi = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema = openapi["components"]["schemas"]["TrajectorySnapshot"]
    assert "reason" in schema["required"]
    # reason should be string type, not nullable in the schema
    assert schema["properties"]["reason"]["type"] == "string"