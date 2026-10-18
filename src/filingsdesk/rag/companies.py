"""Spot which companies a question is about, so retrieval searches only their filings.

Deterministic: tickers as whole words ("NVDA"), the first word of the registrant name
("Apple" from "Apple Inc."), and configured aliases ("Google" for GOOGL).
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from filingsdesk.config import get_settings
from filingsdesk.db import Instrument


def _company_words(instruments: list[tuple[str, str | None]], aliases: str) -> dict[str, set[str]]:
    words: dict[str, set[str]] = {}
    for pair in filter(None, (p.strip() for p in aliases.split(","))):
        symbol, _, alias = pair.partition(":")
        words.setdefault(symbol.strip().upper(), set()).add(alias.strip().lower())
    for symbol, name in instruments:
        if name and name.upper() != symbol:
            # "Amazon.com, Inc." -> amazon
            words.setdefault(symbol, set()).add(re.split(r"[^a-z0-9]", name.lower())[0])
    return words


def match_symbols(
    question: str, instruments: list[tuple[str, str | None]], aliases: str
) -> list[str]:
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    names = _company_words(instruments, aliases)
    return [
        symbol
        for symbol, _ in instruments
        if re.search(rf"\b{re.escape(symbol)}\b", question) or names.get(symbol, set()) & words
    ]


def strip_companies(question: str, instruments: list[tuple[str, str | None]], aliases: str) -> str:
    """The question without company mentions, for keyword search inside one company's
    filings, where "NVIDIA" matches every chunk and drowns out the useful terms."""
    terms = {symbol for symbol, _ in instruments}
    for names in _company_words(instruments, aliases).values():
        terms |= names
    if not terms:
        return question
    alternatives = "|".join(sorted(map(re.escape, terms), key=len, reverse=True))
    return re.sub(rf"\b(?:{alternatives})('s)?\b", " ", question, flags=re.IGNORECASE).strip()


def detect_companies(session: Session, question: str) -> tuple[list[str], str]:
    """(symbols the question names, the question with those mentions removed)."""
    rows = session.execute(select(Instrument.symbol, Instrument.name)).all()
    instruments = [(symbol, name) for symbol, name in rows]
    aliases = get_settings().company_aliases
    symbols = match_symbols(question, instruments, aliases)
    keyword_query = strip_companies(question, instruments, aliases) if symbols else question
    return symbols, keyword_query
