import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from filingsdesk.api.metrics import CACHE_HITS, CACHE_MISSES
from filingsdesk.api.schemas import PriceOut, QuoteOut
from filingsdesk.cache import get_cache
from filingsdesk.config import get_settings
from filingsdesk.db import Instrument, Price
from filingsdesk.db.session import get_session

router = APIRouter(prefix="/prices", tags=["market-data"])


def _instrument_or_404(session: Session, symbol: str) -> Instrument:
    instrument = session.scalars(
        select(Instrument).where(Instrument.symbol == symbol.upper())
    ).one_or_none()
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"unknown instrument: {symbol.upper()}")
    return instrument


@router.get("/{symbol}", response_model=list[PriceOut])
def get_prices(
    symbol: str,
    start: dt.date | None = None,
    end: dt.date | None = None,
    limit: int = Query(default=1000, ge=1, le=10_000),
    session: Session = Depends(get_session),
) -> list[Price]:
    instrument = _instrument_or_404(session, symbol)
    query = select(Price).where(Price.instrument_id == instrument.id)
    if start:
        query = query.where(Price.date >= start)
    if end:
        query = query.where(Price.date <= end)
    return list(session.scalars(query.order_by(Price.date).limit(limit)))


@router.get("/{symbol}/latest", response_model=QuoteOut)
def latest_quote(symbol: str, session: Session = Depends(get_session)) -> QuoteOut:
    """Hot path: cache-aside with TTL (ADR-0002)."""
    key = f"quote:{symbol.upper()}"
    cache = get_cache()
    if (cached := cache.get(key)) is not None:
        CACHE_HITS.inc()
        return QuoteOut(**cached, cached=True)

    CACHE_MISSES.inc()
    instrument = _instrument_or_404(session, symbol)
    price = session.scalars(
        select(Price)
        .where(Price.instrument_id == instrument.id)
        .order_by(Price.date.desc())
        .limit(1)
    ).one_or_none()
    if price is None:
        raise HTTPException(status_code=404, detail=f"no prices for {symbol.upper()}")

    payload = {"symbol": instrument.symbol, "date": price.date.isoformat(), "close": price.close}
    cache.set(key, payload, ttl_seconds=get_settings().quote_cache_ttl_seconds)
    return QuoteOut(symbol=instrument.symbol, date=price.date, close=price.close, cached=False)
