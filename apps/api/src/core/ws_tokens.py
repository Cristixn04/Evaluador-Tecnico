from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import redis.asyncio as redis
from jose import JWTError, jwt

from src.core.config import settings

TOKEN_TYPE_WS = "ws"
WS_TOKEN_TTL_MINUTES = 30


class WSTokenError(Exception):
    pass


class WSTokenExpiredError(WSTokenError):
    pass


class WSTokenInvalidError(WSTokenError):
    pass


class WSTokenRevokedError(WSTokenError):
    pass


class WSTokenService:
    def __init__(self) -> None:
        self._redis: redis.Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def _get_redis(self) -> redis.Redis:
        loop = asyncio.get_running_loop()
        if self._redis is None or self._loop is not loop:
            # redis.asyncio pools are bound to the loop that created them;
            # recreate the client when the running loop changes.
            self._redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            self._loop = loop
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            self._loop = None

    def _token_key(self, jti: str) -> str:
        return f"ws_token:{jti}"

    def _revoked_key(self, jti: str) -> str:
        return f"ws_revoked:{jti}"

    def create_ws_token(self, *, interview_id: UUID, ttl_minutes: int = WS_TOKEN_TTL_MINUTES) -> str:
        """Create a WebSocket JWT token with purpose=ws and session_id=interview_id."""
        now = datetime.now(UTC)
        expire = now + timedelta(minutes=ttl_minutes)
        jti = str(uuid4())

        payload: dict[str, Any] = {
            "sub": str(interview_id),
            "session_id": str(interview_id),
            "purpose": TOKEN_TYPE_WS,
            "type": TOKEN_TYPE_WS,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
        }

        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return token

    async def validate_ws_token(self, token: str) -> UUID:
        """Validate a WebSocket token and return the session_id (interview_id)."""
        redis_client = await self._get_redis()

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError as exc:
            raise WSTokenInvalidError("Invalid token signature") from exc

        if payload.get("type") != TOKEN_TYPE_WS:
            raise WSTokenInvalidError("Invalid token type")

        if payload.get("purpose") != TOKEN_TYPE_WS:
            raise WSTokenInvalidError("Invalid token purpose")

        jti = payload.get("jti")
        if not jti:
            raise WSTokenInvalidError("Missing jti claim")

        # Check if token is revoked
        revoked = await redis_client.get(self._revoked_key(jti))
        if revoked:
            raise WSTokenRevokedError("Token has been revoked")

        # Check if token exists in Redis (valid and not expired)
        token_data = await redis_client.get(self._token_key(jti))
        if not token_data:
            raise WSTokenExpiredError("Token has expired or is invalid")

        # Verify session_id matches
        session_id_str = payload.get("session_id")
        if not session_id_str:
            raise WSTokenInvalidError("Missing session_id claim")

        try:
            session_id = UUID(session_id_str)
        except ValueError as exc:
            raise WSTokenInvalidError("Invalid session_id format") from exc

        return session_id

    async def store_ws_token(self, token: str, ttl_minutes: int = WS_TOKEN_TTL_MINUTES) -> None:
        """Store a WS token in Redis for validation."""
        redis_client = await self._get_redis()

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            return

        jti = payload.get("jti")
        if not jti:
            return

        # Store token metadata with TTL
        await redis_client.setex(
            self._token_key(jti),
            timedelta(minutes=ttl_minutes),
            json.dumps({"session_id": payload.get("session_id")}),
        )

    async def revoke_ws_token(self, token: str) -> None:
        """Revoke a WS token by adding it to the revoked set."""
        redis_client = await self._get_redis()

        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        except JWTError:
            return

        jti = payload.get("jti")
        if not jti:
            return

        # Get remaining TTL
        ttl = await redis_client.ttl(self._token_key(jti))
        if ttl > 0:
            await redis_client.setex(self._revoked_key(jti), ttl, "1")
            await redis_client.delete(self._token_key(jti))

    async def revoke_all_for_session(self, session_id: UUID) -> None:
        """Revoke all WS tokens for a given session (interview)."""
        redis_client = await self._get_redis()

        # Find all tokens for this session
        pattern = "ws_token:*"
        async for key in redis_client.scan_iter(match=pattern):
            data = await redis_client.get(key)
            if data:
                try:
                    token_data = json.loads(data)
                    if token_data.get("session_id") == str(session_id):
                        jti = key.split(":", 1)[1]
                        await redis_client.delete(key)
                        await redis_client.setex(self._revoked_key(jti), WS_TOKEN_TTL_MINUTES * 60, "1")
                except (json.JSONDecodeError, IndexError):
                    continue


# Global instance
ws_token_service = WSTokenService()