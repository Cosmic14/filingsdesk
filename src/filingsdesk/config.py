"""Application configuration, sourced from environment variables / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Empty host = unix socket (local Homebrew Postgres); overridden in CI/compose.
    database_url: str = "postgresql+psycopg:///filingsdesk"

    # Unset → in-memory cache fallback (ADR-0002).
    redis_url: str | None = None
    quote_cache_ttl_seconds: int = 60

    # RAG (ADR-0004/0005/0006)
    vector_backend: str = "auto"  # auto | pgvector | numpy
    embedding_dim: int = 384
    chunking_strategy: str = "section"  # section | fixed
    chunk_size_chars: int = 1600
    chunk_overlap_chars: int = 200
    retrieval_top_k: int = 5
    # Confidence is judged on best-*sentence* similarity (chunk-level cosine is diluted
    # by chunk length). Below refusal floor → refuse as out-of-corpus; below the
    # confidence floor → answer but flag low confidence. Floors chosen empirically on
    # the fixture corpus; the eval harness re-validates them in CI.
    similarity_refusal_floor: float = 0.15
    similarity_confidence_floor: float = 0.30

    # Ingestion
    sec_user_agent: str = "FilingsDesk research project dasabhigyan14@gmail.com"
    ingest_symbols: str = "AAPL,MSFT,NVDA,AMZN,GOOGL"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
