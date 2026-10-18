"""Application configuration, sourced from environment variables / .env."""

from functools import lru_cache

from pydantic import SecretStr
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

    # Answer generation (ADR-0006). Extractive by default so CI stays keyless;
    # "claude" needs ANTHROPIC_API_KEY and falls back to extractive on any API failure.
    # LLM_* rather than CLAUDE_*: Claude Code exports CLAUDE_EFFORT into child shells.
    answer_provider: str = "extractive"  # extractive | claude
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"  # short grounded answers don't need deep thinking
    llm_max_tokens: int = 4096  # thinking counts against this; answers are ~4 claims
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2

    # Ingestion
    sec_user_agent: str = "FilingsDesk research project dasabhigyan14@gmail.com"
    ingest_symbols: str = "AAPL,MSFT,NVDA,AMZN,GOOGL"

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
