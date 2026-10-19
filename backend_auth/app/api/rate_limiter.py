import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import RateLimitSettings
from app.errors import RateLimitExceededError, RateLimitStorageError

logger = logging.getLogger(__name__)

_INCR_WITH_TTL_SCRIPT = """
local current = redis.call("INCR", KEYS[1])
if current == 1 then
    redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
local ttl = redis.call("PTTL", KEYS[1])
return {current, ttl}
"""


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int
    remaining: int
    current_count: int


def _to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, bytes):
        return int(value.decode("utf-8"))
    if isinstance(value, str):
        return int(value)
    raise RateLimitStorageError("Unexpected rate limiter response type")


def ip_per_route_rule(settings: RateLimitSettings) -> RateLimitRule:
    return RateLimitRule(
        name="ip_per_route",
        limit=settings.ip_limit,
        window_seconds=settings.ip_window_seconds,
    )


class RedisFixedWindowRateLimiter:
    def __init__(self, redis: Redis, settings: RateLimitSettings) -> None:
        self.redis = redis
        self.settings = settings

    async def consume(self, rule: RateLimitRule, identity: str) -> RateLimitResult:
        key = f"{self.settings.redis_prefix}:{rule.name}:{identity}"
        window_ms = max(1, rule.window_seconds * 1000)
        try:
            raw_result = cast(
                Sequence[object],
                await self.redis.execute_command("EVAL", _INCR_WITH_TTL_SCRIPT, 1, key, window_ms),
            )
            current_count = _to_int(raw_result[0])
            ttl_ms = _to_int(raw_result[1])
        except RedisError as exc:
            if self.settings.fail_open:
                logger.warning("Rate limiter unavailable; allowing request: %s", exc)
                return RateLimitResult(
                    allowed=True,
                    retry_after_seconds=0,
                    remaining=rule.limit,
                    current_count=0,
                )
            raise RateLimitStorageError() from exc

        ttl_ms = max(ttl_ms, 0)
        retry_after_seconds = math.ceil(ttl_ms / 1000) if ttl_ms > 0 else rule.window_seconds
        remaining = max(rule.limit - current_count, 0)
        allowed = current_count <= rule.limit
        return RateLimitResult(
            allowed=allowed,
            retry_after_seconds=retry_after_seconds,
            remaining=remaining,
            current_count=current_count,
        )


async def enforce_rate_limit(
    rule: RateLimitRule,
    identity: str,
    limiter: RedisFixedWindowRateLimiter,
    enabled: bool,
) -> None:
    if not enabled:
        return
    result = await limiter.consume(rule=rule, identity=identity)
    if result.allowed:
        return
    raise RateLimitExceededError(retry_after_seconds=result.retry_after_seconds)
