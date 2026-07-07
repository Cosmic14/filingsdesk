# ADR-0002: Redis cache-aside with TTL, and graceful degradation

**Status:** accepted · 2026-07-07

## Problem
The hottest read path — "latest quote for symbol X" — is requested far more often than it
changes (daily bars change once a day; intraday at most every few minutes). Hitting
Postgres for every read wastes capacity and adds latency.

## Options
1. **Cache-aside (lazy) with TTL** — API checks Redis; on miss, reads Postgres and writes
   the value back with a TTL.
2. Write-through — ingestion writes to cache and DB together. Keeps cache warm but couples
   the writer to the cache and caches data nobody may read.
3. No cache — simplest, but forfeits the demonstration of a real caching strategy and the
   latency win.

## Decision
Cache-aside with a short TTL (default 60 s for latest-quote, configurable). Invalidation is
by expiry only — for once-a-day bars, a stale window of ≤60 s is harmless, and expiry-only
avoids the classic two-writer invalidation races.

Additionally: the cache is behind a small `Cache` protocol with a Redis implementation and
an **in-memory fallback** used when `REDIS_URL` is unset or Redis is unreachable. The API
must never fail because the cache is down — a cache that can take down the service is worse
than no cache.

## Trade-offs
Cache-aside means the first read after expiry pays the DB round-trip (acceptable at this
traffic). Expiry-only invalidation can serve ≤TTL-stale data — documented and bounded.
In-memory fallback is per-process (no cross-instance sharing) — fine as a degraded mode.
