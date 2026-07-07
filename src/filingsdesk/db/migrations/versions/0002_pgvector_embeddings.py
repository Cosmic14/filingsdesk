"""conditional pgvector: embedding column + HNSW index when the extension is available

If pgvector is not installed on the server (e.g. local Homebrew Postgres), this migration
logs a warning and skips — the app then uses the numpy vector store (ADR-0004).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-07

"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

EMBEDDING_DIM = 384


def _pgvector_available(conn) -> bool:
    return bool(
        conn.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    if not _pgvector_available(conn):
        log.warning(
            "pgvector extension not available on this server — skipping embedding column. "
            "RAG will use the numpy fallback store (ADR-0004)."
        )
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(f"ALTER TABLE filing_chunks ADD COLUMN embedding vector({EMBEDDING_DIM})")
    op.execute(
        "CREATE INDEX ix_chunks_embedding_hnsw ON filing_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    conn = op.get_bind()
    has_col = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'filing_chunks' AND column_name = 'embedding'"
        )
    ).scalar()
    if has_col:
        op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_hnsw")
        op.execute("ALTER TABLE filing_chunks DROP COLUMN embedding")
