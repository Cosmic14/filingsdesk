"""API request/response models. Validation lives here, not in route handlers."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from filingsdesk.backtester import STRATEGIES


class InstrumentOut(BaseModel):
    symbol: str
    name: str | None
    exchange: str | None
    currency: str


class PriceOut(BaseModel):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int | None


class QuoteOut(BaseModel):
    symbol: str
    date: dt.date
    close: float
    cached: bool


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    strategy: Literal[tuple(STRATEGIES)]  # type: ignore[valid-type]
    params: dict[str, int] = Field(default_factory=dict)
    cost_bps: float = Field(default=10.0, ge=0, le=500)
    initial_capital: float = Field(default=10_000.0, gt=0)
    start: dt.date | None = None
    end: dt.date | None = None


class EquityPoint(BaseModel):
    date: dt.date
    equity: float


class BacktestResponse(BaseModel):
    symbol: str
    strategy: str
    params: dict[str, int]
    metrics: dict[str, float]
    equity_curve: list[EquityPoint]


class CitationOut(BaseModel):
    marker: int
    accession_no: str
    symbol: str | None
    form_type: str
    section: str | None
    similarity: float


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    confidence: str
    refused: bool
    injection_flagged: bool
    answered_by: str
