from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from filingsdesk.api.schemas import InstrumentOut
from filingsdesk.db import Instrument
from filingsdesk.db.session import get_session

router = APIRouter(prefix="/instruments", tags=["market-data"])


@router.get("", response_model=list[InstrumentOut])
def list_instruments(session: Session = Depends(get_session)) -> list[Instrument]:
    return list(session.scalars(select(Instrument).order_by(Instrument.symbol)))
