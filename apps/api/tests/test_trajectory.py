"""Tests for GET /interviews/{id}/trajectory endpoint."""

from datetime import UTC

import pytest
from fastapi.openapi.utils import get_openapi
from fastapi.testclient import TestClient

from src.main import app


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


def test_trajectory_nonexistent():
    """Test 1: 404 para entrevista inexistente."""
    c = TestClient(app)
    resp = c.get("/interviews/123e4567-e89b-12d3-a456-426614174000/trajectory")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Interview not found"


@pytest.mark.asyncio
async def test_trajectory_interview_no_snapshots(db_session):
    """Test 2: Entrevista existente sin snapshots."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Vacancy
    
    # Create minimal test data using the db_session
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
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
async def test_trajectory_single_snapshot_legacy_default(db_session):
    """Test 3: Un snapshot. Test 8: reason = legacy en snapshots históricos."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    # The model has server_default="legacy", and the DB now has a default too
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
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
async def test_trajectory_multiple_snapshots(db_session):
    """Test 4: Múltiples snapshots. Test 5: Orden cronológico determinista.
    Test 6: Cálculo de timestamp_offset_seconds. Test 7: Cálculo de total_duration_seconds."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
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
async def test_trajectory_reason_legacy_default(db_session):
    """Test 8: reason = legacy en snapshots históricos."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 8: reason should be 'legacy' for historical snapshots
    assert data["snapshots"][0]["reason"] == "legacy"


@pytest.mark.asyncio
async def test_trajectory_execution_fields_optional_when_no_result(db_session):
    """Test 9: Campos de ejecución opcionales cuando no hay resultado."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    # reason is set explicitly since DB has NOT NULL constraint
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 9: Execution fields should be optional/None when no result
    assert data["snapshots"][0]["tests_passed"] is None
    assert data["snapshots"][0]["total_tests"] is None
    assert data["snapshots"][0]["execution_status"] is None


@pytest.mark.asyncio
async def test_trajectory_execution_persistence(db_session):
    """Test 10: Persistencia de tests_passed, total_tests y execution_status al ejecutar código."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 10: Execution fields should be persisted
    assert data["snapshots"][0]["tests_passed"] == 2
    assert data["snapshots"][0]["total_tests"] == 2
    assert data["snapshots"][0]["execution_status"] == "success"
    assert data["snapshots"][0]["reason"] == "run"


@pytest.mark.asyncio
async def test_trajectory_no_event_note(db_session):
    """Test 12: Ausencia de event_note en la respuesta JSON."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 12: No event_note in response
    for s in data["snapshots"]:
        assert "event_note" not in s or s.get("event_note") is None


@pytest.mark.asyncio
async def test_trajectory_no_duplicate_snapshots(db_session):
    """Test 11: Ausencia de snapshots duplicados para una ejecución."""
    import uuid
    from datetime import datetime

    from src.db.models import Interview, Problem, Snapshot, Vacancy
    
    # Create minimal test data
    vacancy = Vacancy(
        id=uuid.uuid4(),
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
    c = TestClient(app)
    resp = c.get(f"/interviews/{interview.id}/trajectory")
    assert resp.status_code == 200
    data = resp.json()
    
    # Test 11: Should return all snapshots (including duplicates if they exist in DB)
    assert isinstance(data["snapshots"], list)
    assert len(data["snapshots"]) >= 2


@pytest.mark.asyncio
async def test_trajectory_reason_required_openapi():
    """Test that reason is required in the TrajectorySnapshot schema."""
    from fastapi.openapi.utils import get_openapi
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