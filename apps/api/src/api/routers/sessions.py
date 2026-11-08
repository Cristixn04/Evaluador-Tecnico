from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.invitations import AnonymousCandidateSession, ProblemSummary
from src.core.rate_limit import get_rate_limiter
from src.core.ws_tokens import ws_token_service
from src.db.models import Problem, Vacancy
from src.db.session import get_db
from src.interview.service import InterviewService

router = APIRouter(prefix="/sessions", tags=["Sessions"])


def get_client_ip(request: Request) -> str:
    """Extract client IP from request, respecting proxy headers."""
    # Check for forwarded header (when behind proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (client IP)
        return forwarded_for.split(",")[0].strip()
    # Check for real IP header (some proxies)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    # Fallback to client host
    return request.client.host if request.client else "unknown"


def _build_ws_url(request: Request, interview_id: str) -> str:
    """Construct canonical WebSocket URL from incoming HTTP request."""
    forwarded_proto = request.headers.get("x-forwarded-proto")
    is_secure = forwarded_proto == "https" if forwarded_proto else request.url.scheme == "https"
    ws_scheme = "wss" if is_secure else "ws"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{ws_scheme}://{host}/ws/interview/{interview_id}"


@router.get("/verify", response_model=AnonymousCandidateSession)
async def verify_candidate_session(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    token: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
) -> AnonymousCandidateSession:
    auth_token: str | None = None
    if authorization and authorization.startswith("Bearer "):
        auth_token = authorization[7:].strip()
    elif token:
        auth_token = token.strip()

    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )

    # Rate limiting: 10 requests per 60 seconds per IP + selector
    get_rate_limiter()
    client_ip = get_client_ip(request)
    allowed, _remaining = await get_rate_limiter().check_limit_with_ip(
        selector=auth_token[:16],
        ip=client_ip,
        limit=10,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    interview_service = InterviewService(session)

    try:
        interview = await interview_service.get_or_create_from_invitation(auth_token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from e

    # Load vacancy for title
    vacancy = await session.get(Vacancy, interview.vacancy_id)

    # Generate masked candidate ID
    masked_candidate_id = f"CAND-{interview.id.hex[:4].upper()}"

    # Get problem summary
    if not interview.problem_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Interview has no assigned problem",
        )
    problem = await session.get(Problem, interview.problem_id)
    if not problem:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Problem not found",
        )

    problem_summary = ProblemSummary(
        id=str(problem.id),
        title=problem.title,
        difficulty=problem.difficulty.value if hasattr(problem.difficulty, "value") else str(problem.difficulty),
        language=problem.language,
        scenario_preview=problem.scenario_preview,
        tags=problem.tags,
    )

    # Generate WS token
    ws_token = ws_token_service.create_ws_token(interview_id=interview.id)
    await ws_token_service.store_ws_token(ws_token)

    ws_url = _build_ws_url(request, str(interview.id))

    return AnonymousCandidateSession(
        session_id=str(interview.id),
        masked_candidate_id=masked_candidate_id,
        vacancy_title=vacancy.title if vacancy else "Unknown Vacancy",
        current_phase=interview.phase.value,
        status=interview.status.value,
        problem=problem_summary,
        ws_token=ws_token,
        ws_url=ws_url,
    )