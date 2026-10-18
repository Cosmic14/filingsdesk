"""full-text search column for hybrid retrieval

A generated tsvector over each chunk, GIN-indexed. Keyword search catches exact terms
("employees", "repurchases") that small embedding models blur together; the vector store
fuses both rankings (ADR-0008).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-18

"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE filing_chunks ADD COLUMN search_tsv tsvector "
        "GENERATED ALWAYS AS (to_tsvector('english', text)) STORED"
    )
    op.execute("CREATE INDEX ix_chunks_search_tsv ON filing_chunks USING gin (search_tsv)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_search_tsv")
    op.execute("ALTER TABLE filing_chunks DROP COLUMN IF EXISTS search_tsv")
