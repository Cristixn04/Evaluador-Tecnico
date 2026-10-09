from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
from jose import JWTError, jwt  # type: ignore[import-untyped]

from src.core.config import settings
from src.db.enums import UserRole

TOKEN_TYPE_ACCESS = "access"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(
    *,
    user_id: UUID,
    organization_id: UUID,
    role: UserRole,
    expires_delta: timedelta | None = None,
) -> str:
    minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(UTC) + (
        expires_delta if expires_delta is not None else timedelta(minutes=minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "organization_id": str(organization_id),
        "role": role.value,
        "type": TOKEN_TYPE_ACCESS,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise ValueError("invalid token") from exc

    if payload.get("type") != TOKEN_TYPE_ACCESS:
        raise ValueError("invalid token type")
    return payload
