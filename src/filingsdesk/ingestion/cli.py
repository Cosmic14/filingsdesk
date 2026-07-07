"""`filingsdesk-ingest` — run one ingestion pass (live APIs or offline fixtures)."""

import argparse

from filingsdesk.logging_setup import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest prices and SEC filings")
    parser.add_argument("--symbols", help="comma-separated tickers (default from settings)")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="use bundled deterministic fixtures instead of live APIs (offline demo/CI)",
    )
    parser.add_argument("--no-filings", action="store_true", help="prices only")
    args = parser.parse_args()

    configure_logging()
    from filingsdesk.ingestion.service import run_ingestion

    totals = run_ingestion(
        symbols=args.symbols.split(",") if args.symbols else None,
        days=args.days,
        fixtures=args.fixtures,
        with_filings=not args.no_filings,
    )
    print(f"ingested: {totals}")


if __name__ == "__main__":
    main()
