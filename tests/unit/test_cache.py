"""Cache semantics: TTL expiry, miss behaviour, fallback selection (ADR-0002)."""

import filingsdesk.cache.backends as backends
from filingsdesk.cache import InMemoryCache, get_cache


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_miss_returns_none():
    cache = InMemoryCache(clock=FakeClock())
    assert cache.get("absent") is None


def test_set_then_get_within_ttl():
    clock = FakeClock()
    cache = InMemoryCache(clock=clock)
    cache.set("quote:AAPL", {"close": 190.5}, ttl_seconds=60)
    clock.advance(59)
    assert cache.get("quote:AAPL") == {"close": 190.5}


def test_expires_exactly_at_ttl():
    clock = FakeClock()
    cache = InMemoryCache(clock=clock)
    cache.set("k", "v", ttl_seconds=60)
    clock.advance(60)
    assert cache.get("k") is None


def test_overwrite_resets_ttl():
    clock = FakeClock()
    cache = InMemoryCache(clock=clock)
    cache.set("k", "v1", ttl_seconds=10)
    clock.advance(8)
    cache.set("k", "v2", ttl_seconds=10)
    clock.advance(8)
    assert cache.get("k") == "v2"


def test_expired_entry_is_evicted_on_read():
    clock = FakeClock()
    cache = InMemoryCache(clock=clock)
    cache.set("k", "v", ttl_seconds=1)
    clock.advance(2)
    cache.get("k")
    assert "k" not in cache._data


def test_get_cache_falls_back_to_memory_when_redis_unset(monkeypatch):
    monkeypatch.setattr(backends, "_cache", None)
    monkeypatch.delenv("REDIS_URL", raising=False)
    backends.get_settings.cache_clear()
    assert isinstance(get_cache(), InMemoryCache)


def test_get_cache_falls_back_when_redis_unreachable(monkeypatch):
    monkeypatch.setattr(backends, "_cache", None)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:1")  # nothing listens on port 1
    backends.get_settings.cache_clear()
    try:
        assert isinstance(get_cache(), InMemoryCache)
    finally:
        backends.get_settings.cache_clear()
