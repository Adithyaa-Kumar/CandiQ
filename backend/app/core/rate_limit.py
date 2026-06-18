"""
rate_limit.py
─────────────
Simple fixed-window rate limiter backed by Redis. Protects the
/jobs endpoint (and others) from a single user firing enough requests
to exhaust the Anthropic API budget or DB connections.

Window: 60 seconds. Limit: settings.rate_limit_per_minute per user (by user id)
or per IP for unauthenticated routes.
"""

import redis

from app.config import get_settings

settings = get_settings()
_redis_client = redis.from_url(settings.redis_url, decode_responses=True)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


def check_rate_limit(key: str, limit: int | None = None, window_seconds: int = 60) -> None:
    """
    Raises RateLimitExceeded if `key` has exceeded `limit` requests in the
    current window. Uses Redis INCR + TTL — atomic, no race conditions.
    """
    limit = limit or settings.rate_limit_per_minute
    redis_key = f"ratelimit:{key}"

    current = _redis_client.incr(redis_key)
    if current == 1:
        _redis_client.expire(redis_key, window_seconds)

    if current > limit:
        ttl = _redis_client.ttl(redis_key)
        raise RateLimitExceeded(retry_after=max(ttl, 1))
