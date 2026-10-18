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

# Source checkout first; an installed wheel lives in site-packages, so containers fall
# back to the working directory (the Dockerfile copies data/ into /app).
_SOURCE_FIXTURES = Path(__file__).resolve().parents[3] / "data" / "fixtures" / "filings"
FIXTURES_DIR = (
    _SOURCE_FIXTURES if _SOURCE_FIXTURES.is_dir() else Path.cwd() / "data" / "fixtures" / "filings"
)


@dataclass(frozen=True)
class FilingRecord:
    accession_no: str
    symbol: str
    form_type: str
    filed_at: dt.datetime
    title: str
    body: str
    source_url: str | None = None
    company: str | None = None  # EDGAR's registrant name, e.g. "Apple Inc."


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
    # ix:header is the hidden inline-XBRL fact block at the top of every modern filing.
    _SKIP = {"script", "style", "ix:header"}
    # Without breaks at block boundaries, "...2026.Rest of Asia" runs together and the
    # "ITEM 1A" lines that section-aware chunking keys on disappear.
    _BLOCK = {"p", "div", "br", "tr", "li", "table", "h1", "h2", "h3", "h4", "h5", "h6"}
    _CELL = {"td", "th"}

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self._parts.append("\n")
        elif tag in self._CELL:
            self._parts.append(" | ")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts).replace("\xa0", " ")
        lines = (re.sub(r"[ \t]+", " ", line).strip(" |") for line in raw.split("\n"))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return extractor.text()


@retry(stop=stop_after_attempt(4), wait=wait_exponential_jitter(initial=1, max=30), reraise=True)
def _get(client: httpx.Client, url: str) -> httpx.Response:
    response = client.get(url)
    response.raise_for_status()
    return response


DEFAULT_PER_FORM = {"10-K": 1, "10-Q": 2}  # latest annual report + two latest quarters


def select_latest(rows: list[dict], per_form: dict[str, int]) -> list[dict]:
    """First N rows of each form; EDGAR lists `filings.recent` newest first."""
    taken: dict[str, int] = {}
    selected = []
    for row in rows:
        if taken.get(row["form_type"], 0) < per_form.get(row["form_type"], 0):
            taken[row["form_type"]] = taken.get(row["form_type"], 0) + 1
            selected.append(row)
    return selected


def fetch_recent_filings(symbol: str, per_form: dict[str, int] | None = None) -> list[FilingRecord]:
    """Fetch the latest filings per form type for a ticker (default: 1 x 10-K, 2 x 10-Q)."""
    per_form = per_form or DEFAULT_PER_FORM
    forms = set(per_form)
    headers = {"User-Agent": get_settings().sec_user_agent}
    with httpx.Client(headers=headers, timeout=30) as client:
        tickers = _get(client, EDGAR_TICKERS_URL).json()
        match = next((row for row in tickers.values() if row["ticker"] == symbol.upper()), None)
        if match is None:
            log.warning("filings.unknown_ticker", symbol=symbol)
            return []
        cik, company = match["cik_str"], match.get("title")

        payload = _get(client, EDGAR_SUBMISSIONS_URL.format(cik=cik)).json()
        rows = select_latest(parse_submissions(payload, symbol, forms), per_form)

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
                    filed_at=dt.datetime.fromisoformat(row["filing_date"]).replace(tzinfo=dt.UTC),
                    title=row["description"],
                    body=body,
                    source_url=doc_url,
                    company=company,
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
    if not records:
        raise FileNotFoundError(f"no fixture filings found in {FIXTURES_DIR}")
    return records
