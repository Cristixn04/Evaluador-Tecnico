from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import decode_access_token
from src.db.enums import UserRole
from src.db.models import Membership, User
from src.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user: User
    membership: Membership
    user_id: UUID
    organization_id: UUID
    role: UserRole


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> AuthenticatedPrincipal:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["organization_id"]))
        role = UserRole(str(payload["role"]))
    except (ValueError, KeyError, TypeError):
        raise credentials_exception from None

    result = await session.execute(
        select(User).options(selectinload(User.memberships)).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception

    membership = next(
        (
            item
            for item in user.memberships
            if item.organization_id == organization_id and item.role == role
        ),
        None,
    )
    if membership is None:
        raise credentials_exception

    return AuthenticatedPrincipal(
        user=user,
        membership=membership,
        user_id=user.id,
        organization_id=membership.organization_id,
        role=membership.role,
    )


def require_role(*roles: UserRole) -> Callable[..., Awaitable[AuthenticatedPrincipal]]:
    allowed = set(roles)

    async def _require_role(
        principal: AuthenticatedPrincipal = Depends(get_current_user),
    ) -> AuthenticatedPrincipal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return principal

    return _require_role


def require_organization(
    organization_id: UUID,
    principal: AuthenticatedPrincipal,
) -> None:
    if principal.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization mismatch",
        )
