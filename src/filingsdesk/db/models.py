"""Relational schema: instruments 1→N prices, instruments 1→N filings 1→N chunks.

The `filing_chunks.embedding` vector column is added by a conditional migration and is
deliberately NOT mapped here: local databases without pgvector don't have it, and the
pgvector store reads/writes it via SQL (ADR-0004). The ORM never touches it.
"""

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(256))
    exchange: Mapped[str | None] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    prices: Mapped[list["Price"]] = relationship(back_populates="instrument")
    filings: Mapped[list["Filing"]] = relationship(back_populates="instrument")


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (
        UniqueConstraint("instrument_id", "date", name="uq_prices_instrument_date"),
        Index("ix_prices_instrument_date_desc", "instrument_id", "date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id", ondelete="CASCADE"))
    date: Mapped[dt.date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column(BigInteger)

    instrument: Mapped[Instrument] = relationship(back_populates="prices")


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (Index("ix_filings_instrument_filed", "instrument_id", "filed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    accession_no: Mapped[str] = mapped_column(String(32), unique=True)
    instrument_id: Mapped[int | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="SET NULL")
    )
    form_type: Mapped[str] = mapped_column(String(16), index=True)
    filed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1024))

    instrument: Mapped[Instrument | None] = relationship(back_populates="filings")
    chunks: Mapped[list["FilingChunk"]] = relationship(
        back_populates="filing", cascade="all, delete-orphan"
    )


class FilingChunk(Base):
    __tablename__ = "filing_chunks"
    __table_args__ = (UniqueConstraint("filing_id", "chunk_index", name="uq_chunks_filing_index"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    section: Mapped[str | None] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)

    filing: Mapped[Filing] = relationship(back_populates="chunks")
