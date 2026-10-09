from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.schemas.auth import AuthToken, LoginRequest
from src.core.security import create_access_token, verify_password
from src.db.models import User
from src.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=AuthToken)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db),
) -> AuthToken:
    result = await session.execute(
        select(User)
        .options(selectinload(User.memberships))
        .where(User.email == payload.email.lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    if not user.memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no organization membership",
        )

    membership = min(user.memberships, key=lambda item: item.created_at)
    token = create_access_token(
        user_id=user.id,
        organization_id=membership.organization_id,
        role=membership.role,
    )
    return AuthToken(
        access_token=token,
        token_type="bearer",
        role=membership.role,
        organization_id=str(membership.organization_id),
    )
