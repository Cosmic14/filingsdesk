"""EDGAR payload parsing and HTML text extraction — pure functions, no network."""

from filingsdesk.ingestion.filings import (
    html_to_text,
    load_fixture_filings,
    parse_submissions,
    select_latest,
)

SUBMISSIONS_PAYLOAD = {
    "filings": {
        "recent": {
            "accessionNumber": ["0001-26-1", "0001-26-2", "0001-26-3"],
            "form": ["10-K", "8-K", "10-Q"],
            "filingDate": ["2026-01-15", "2026-02-01", "2026-04-30"],
            "primaryDocument": ["a10k.htm", "an8k.htm", "a10q.htm"],
            "primaryDocDescription": ["Annual report", "", "Quarterly report"],
        }
    }
}


def test_parse_submissions_filters_forms():
    rows = parse_submissions(SUBMISSIONS_PAYLOAD, "AAPL", forms={"10-K", "10-Q"})
    assert [row["accession_no"] for row in rows] == ["0001-26-1", "0001-26-3"]
    assert rows[0]["form_type"] == "10-K"
    assert rows[0]["primary_doc"] == "a10k.htm"


def test_parse_submissions_fills_missing_description():
    rows = parse_submissions(SUBMISSIONS_PAYLOAD, "AAPL", forms={"8-K"})
    assert rows[0]["description"] == "AAPL 8-K"


def test_parse_submissions_empty_payload():
    assert parse_submissions({}, "AAPL", forms={"10-K"}) == []


def test_html_to_text_strips_tags_and_scripts():
    html = (
        "<html><head><script>var x = 1;</script><style>p{}</style></head>"
        "<body><h1>ITEM 1. BUSINESS</h1><p>We sell   things.</p></body></html>"
    )
    text = html_to_text(html)
    assert "ITEM 1. BUSINESS" in text
    assert "We sell things." in text
    assert "var x" not in text
    assert "p{}" not in text


def test_html_to_text_keeps_block_and_cell_boundaries():
    html = (
        "<body><ix:header><ix:hidden>dei:EntityName</ix:hidden></ix:header>"
        "<div>Japan net sales fell in 2026.</div><div>Rest of Asia rose.</div>"
        "<h2>ITEM 1A. RISK FACTORS</h2>"
        "<table><tr><td>Services</td><td>$&#160;30,739</td></tr></table></body>"
    )
    lines = html_to_text(html).splitlines()
    assert "Japan net sales fell in 2026." in lines  # no longer "2026.Rest of Asia"
    assert "ITEM 1A. RISK FACTORS" in lines  # section-aware chunking keys on this line
    assert "Services | $ 30,739" in lines
    assert "EntityName" not in html_to_text(html)


def test_select_latest_takes_newest_per_form():
    rows = [
        {"form_type": f, "accession_no": a}
        for f, a in [("10-Q", "q3"), ("8-K", "x"), ("10-Q", "q2"), ("10-Q", "q1"), ("10-K", "k")]
    ]
    picked = select_latest(rows, {"10-K": 1, "10-Q": 2})
    assert [r["accession_no"] for r in picked] == ["q3", "q2", "k"]


def test_fixture_filings_load_and_are_labelled_synthetic():
    records = load_fixture_filings()
    assert len(records) == 5
    assert {r.symbol for r in records} == {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"}
    for record in records:
        assert "SYNTHETIC FIXTURE" in record.body
        assert record.accession_no
        assert record.filed_at.tzinfo is not None


def test_fixture_filings_load():
    from filingsdesk.ingestion.filings import load_fixture_filings

    assert len(load_fixture_filings()) == 5


def test_missing_fixtures_fail_loudly(tmp_path, monkeypatch):
    # A wrong path used to glob nothing and ingest zero filings without a word.
    import pytest

    from filingsdesk.ingestion import filings

    monkeypatch.setattr(filings, "FIXTURES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        filings.load_fixture_filings()
