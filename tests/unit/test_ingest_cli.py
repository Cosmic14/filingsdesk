"""CLI argument wiring — the entrypoint calls the service with what the user asked."""

import sys

import filingsdesk.ingestion.cli as cli


def test_cli_passes_flags_through(monkeypatch, capsys):
    captured = {}

    def fake_run_ingestion(**kwargs):
        captured.update(kwargs)
        return {"prices": 0, "filings": 0}

    import filingsdesk.ingestion.service as service

    monkeypatch.setattr(service, "run_ingestion", fake_run_ingestion)
    monkeypatch.setattr(
        sys, "argv", ["filingsdesk-ingest", "--fixtures", "--symbols", "AAPL,MSFT", "--no-filings"]
    )
    cli.main()

    assert captured == {
        "symbols": ["AAPL", "MSFT"],
        "days": 365,
        "fixtures": True,
        "with_filings": False,
    }
    assert "ingested" in capsys.readouterr().out
