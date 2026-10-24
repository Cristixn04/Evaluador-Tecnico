from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
import time
from typing import TYPE_CHECKING

import redis.asyncio as redis

if TYPE_CHECKING:
    from src.core.config import Settings


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._redis_url = settings.REDIS_URL
        self._redis: redis.Redis | None = None

    async def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def check_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Sliding window rate limit using Redis sorted set.
        Returns (allowed, remaining_requests).
        """
        redis_client = await self._get_redis()
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = redis_client.pipeline()
            # Remove expired entries
            pipe.zremrangebyscore(key, 0, window_start)
            # Count current
            pipe.zcard(key)
            # Add current request
            pipe.zadd(key, {f"{now}:{time.time_ns()}": now})
            # Set expiry
            pipe.expire(key, window_seconds + 1)
            results = await pipe.execute()

            current_count = results[1]
            if current_count >= limit:
                return False, 0
            return True, limit - current_count - 1
        except Exception:
            # Fail-open: log and allow
            logger.warning("Rate limiter Redis error, failing open", exc_info=True)
            return True, limit

    async def check_limit_with_ip(
        self,
        selector: str,
        ip: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """
        Check rate limit with both selector and IP.
        Uses a composite key: verify:{selector}:ip:{hashed_ip}
        """
        import hashlib
        
        # Hash IP for privacy (don't store raw IP in Redis keys)
        hashed_ip = hashlib.sha256(ip.encode()).hexdigest()[:16]
        key = f"verify:{selector}:ip:{hashed_ip}"
        
        return await self.check_limit(key, limit, window_seconds)


# Global instance (lazy init)
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        from src.core.config import settings
        _rate_limiter = RateLimiter(settings)
    return _rate_limiter