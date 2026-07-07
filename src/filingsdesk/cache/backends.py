"""Cache-aside layer (ADR-0002).

`RedisCache` when REDIS_URL is configured and reachable; `InMemoryCache` otherwise.
The API must never fail because the cache is down, so `get_cache` degrades silently
(with a log line) rather than raising.
"""

import json
import time
from typing import Any, Protocol

import structlog

from filingsdesk.config import get_settings

log = structlog.get_logger(__name__)


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class InMemoryCache:
    """Per-process TTL cache. Degraded mode / tests. Injectable clock for testability."""

    def __init__(self, clock=time.monotonic) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._clock = clock

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if self._clock() >= expires_at:
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._data[key] = (self._clock() + ttl_seconds, value)


class RedisCache:
    """JSON-serialising cache on Redis with native TTL (SETEX)."""

    def __init__(self, url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)

    def ping(self) -> bool:
        return bool(self._client.ping())

    def get(self, key: str) -> Any | None:
        raw = self._client.get(key)
        return None if raw is None else json.loads(raw)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, json.dumps(value))


_cache: Cache | None = None


def get_cache() -> Cache:
    """Process-wide cache instance; Redis if configured and reachable, else in-memory."""
    global _cache
    if _cache is None:
        url = get_settings().redis_url
        if url:
            try:
                candidate = RedisCache(url)
                candidate.ping()
                _cache = candidate
                log.info("cache.backend", backend="redis")
            except Exception as exc:
                log.warning("cache.redis_unreachable_falling_back", error=str(exc))
                _cache = InMemoryCache()
        else:
            log.info("cache.backend", backend="memory")
            _cache = InMemoryCache()
    return _cache
