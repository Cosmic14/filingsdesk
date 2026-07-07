"""core schema: instruments, prices, filings, filing_chunks

Revision ID: 0001
Revises:
Create Date: 2026-07-07

"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("name", sa.String(256)),
        sa.Column("exchange", sa.String(32)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"], unique=True)

    op.create_table(
        "prices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "instrument_id",
            sa.Integer(),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger()),
        sa.UniqueConstraint("instrument_id", "date", name="uq_prices_instrument_date"),
    )
    op.create_index("ix_prices_instrument_date_desc", "prices", ["instrument_id", "date"])

    op.create_table(
        "filings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("accession_no", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="SET NULL")
        ),
        sa.Column("form_type", sa.String(16), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(512)),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(1024)),
    )
    op.create_index("ix_filings_form_type", "filings", ["form_type"])
    op.create_index("ix_filings_instrument_filed", "filings", ["instrument_id", "filed_at"])

    op.create_table(
        "filing_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "filing_id",
            sa.Integer(),
            sa.ForeignKey("filings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(128)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.UniqueConstraint("filing_id", "chunk_index", name="uq_chunks_filing_index"),
    )


def downgrade() -> None:
    op.drop_table("filing_chunks")
    op.drop_table("filings")
    op.drop_table("prices")
    op.drop_table("instruments")
