import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from filingsdesk.api.schemas import BacktestRequest, BacktestResponse, EquityPoint
from filingsdesk.backtester import STRATEGIES, run_backtest
from filingsdesk.db import Instrument, Price
from filingsdesk.db.session import get_session

router = APIRouter(prefix="/backtest", tags=["backtesting"])

MIN_BARS = 30


@router.post("", response_model=BacktestResponse)
def backtest(request: BacktestRequest, session: Session = Depends(get_session)) -> BacktestResponse:
    instrument = session.scalars(
        select(Instrument).where(Instrument.symbol == request.symbol.upper())
    ).one_or_none()
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"unknown instrument: {request.symbol.upper()}")

    query = (
        select(Price.date, Price.close)
        .where(Price.instrument_id == instrument.id)
        .order_by(Price.date)
    )
    if request.start:
        query = query.where(Price.date >= request.start)
    if request.end:
        query = query.where(Price.date <= request.end)
    rows = session.execute(query).all()
    if len(rows) < MIN_BARS:
        raise HTTPException(
            status_code=422,
            detail=f"need at least {MIN_BARS} bars, found {len(rows)} — ingest prices first",
        )

    prices = pd.Series(
        [row.close for row in rows], index=pd.DatetimeIndex([row.date for row in rows])
    )
    try:
        signal = STRATEGIES[request.strategy](prices, **request.params)
        result = run_backtest(
            prices, signal, cost_bps=request.cost_bps, initial_capital=request.initial_capital
        )
    except (ValueError, TypeError) as exc:  # bad strategy params surface as 422, not 500
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return BacktestResponse(
        symbol=instrument.symbol,
        strategy=request.strategy,
        params=request.params,
        metrics={k: round(v, 6) for k, v in result.metrics.items()},
        equity_curve=[
            EquityPoint(date=index.date(), equity=round(value, 2))
            for index, value in result.equity_curve.items()
        ],
    )
