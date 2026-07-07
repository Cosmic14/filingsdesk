"""EDGAR payload parsing and HTML text extraction — pure functions, no network."""

from filingsdesk.ingestion.filings import html_to_text, load_fixture_filings, parse_submissions

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


def test_fixture_filings_load_and_are_labelled_synthetic():
    records = load_fixture_filings()
    assert len(records) == 5
    assert {r.symbol for r in records} == {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL"}
    for record in records:
        assert "SYNTHETIC FIXTURE" in record.body
        assert record.accession_no
        assert record.filed_at.tzinfo is not None
