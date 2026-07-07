"""SEC EDGAR filings client + offline fixture loader.

EDGAR asks for a descriptive User-Agent and ≤10 req/s; we send the configured UA and
retry with backoff. Parsing is separated from fetching so it is unit-testable offline.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from filingsdesk.config import get_settings

log = structlog.get_logger(__name__)

EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
EDGAR_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}"

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "filings"


@dataclass(frozen=True)
class FilingRecord:
    accession_no: str
    symbol: str
    form_type: str
    filed_at: dt.datetime
    title: str
    body: str
    source_url: str | None = None


def parse_submissions(payload: dict, symbol: str, forms: set[str]) -> list[dict]:
    """Extract filing metadata rows from an EDGAR submissions JSON payload.

    Pure function over the documented columnar `filings.recent` layout.
    """
    recent = payload.get("filings", {}).get("recent", {})
    rows = zip(
        recent.get("accessionNumber", []),
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("primaryDocument", []),
        recent.get("primaryDocDescription", []),
        strict=True,
    )
    out = []
    for accession, form, filing_date, primary_doc, description in rows:
        if form in forms:
            out.append(
                {
                    "accession_no": accession,
                    "symbol": symbol,
                    "form_type": form,
                    "filing_date": filing_date,
                    "primary_doc": primary_doc,
                    "description": description or f"{symbol} {form}",
                }
            )
    return out


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", raw)).strip()


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text()


@retry(stop=stop_after_attempt(4), wait=wait_exponential_jitter(initial=1, max=30), reraise=True)
def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


def fetch_recent_filings(
    symbol: str, forms: set[str] | None = None, limit: int = 3
) -> list[FilingRecord]:
    """Fetch the most recent `limit` filings of the given forms for a ticker."""
    forms = forms or {"10-K", "10-Q"}
    headers = {"User-Agent": get_settings().sec_user_agent}
    with httpx.Client(headers=headers, timeout=30) as client:
        tickers = _get(client, EDGAR_TICKERS_URL).json()
        cik = next(
            (row["cik_str"] for row in tickers.values() if row["ticker"] == symbol.upper()),
            None,
        )
        if cik is None:
            log.warning("filings.unknown_ticker", symbol=symbol)
            return []

        payload = _get(client, EDGAR_SUBMISSIONS_URL.format(cik=cik)).json()
        rows = parse_submissions(payload, symbol, forms)[:limit]

        records = []
        for row in rows:
            doc_url = EDGAR_DOC_URL.format(
                cik=cik,
                accession_nodash=row["accession_no"].replace("-", ""),
                doc=row["primary_doc"],
            )
            body = html_to_text(_get(client, doc_url).text)
            records.append(
                FilingRecord(
                    accession_no=row["accession_no"],
                    symbol=symbol,
                    form_type=row["form_type"],
                    filed_at=dt.datetime.fromisoformat(row["filing_date"]).replace(
                        tzinfo=dt.UTC
                    ),
                    title=row["description"],
                    body=body,
                    source_url=doc_url,
                )
            )
            log.info("filings.fetched", symbol=symbol, accession=row["accession_no"])
        return records


def load_fixture_filings() -> list[FilingRecord]:
    """Bundled synthetic filing excerpts — offline demo/CI corpus (clearly labelled)."""
    records = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        records.append(
            FilingRecord(
                accession_no=data["accession_no"],
                symbol=data["symbol"],
                form_type=data["form_type"],
                filed_at=dt.datetime.fromisoformat(data["filed_at"]),
                title=data["title"],
                body=data["body"],
                source_url=data.get("source_url"),
            )
        )
    return records
