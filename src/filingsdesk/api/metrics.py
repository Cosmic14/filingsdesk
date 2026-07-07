"""Prometheus metrics: request rate/latency by route template, cache effectiveness."""

from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "filingsdesk_http_requests_total",
    "HTTP requests",
    labelnames=("method", "route", "status"),
)
REQUEST_LATENCY = Histogram(
    "filingsdesk_http_request_seconds",
    "HTTP request latency",
    labelnames=("method", "route"),
)
CACHE_HITS = Counter("filingsdesk_cache_hits_total", "Quote cache hits")
CACHE_MISSES = Counter("filingsdesk_cache_misses_total", "Quote cache misses")
