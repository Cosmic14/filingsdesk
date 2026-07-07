"""Ingestion worker: runs a daily pass on a schedule (container entrypoint)."""

import os

import structlog
from apscheduler.schedulers.blocking import BlockingScheduler

from filingsdesk.ingestion.service import run_ingestion
from filingsdesk.logging_setup import configure_logging

log = structlog.get_logger(__name__)


def main() -> None:
    configure_logging()
    fixtures = os.environ.get("INGEST_FIXTURES", "0") == "1"
    hour = int(os.environ.get("INGEST_HOUR_UTC", "22"))  # after US close

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        run_ingestion,
        "cron",
        hour=hour,
        kwargs={"fixtures": fixtures},
        misfire_grace_time=3600,
    )
    log.info("scheduler.start", hour_utc=hour, fixtures=fixtures)
    run_ingestion(fixtures=fixtures)  # one pass at startup so a fresh stack has data
    scheduler.start()


if __name__ == "__main__":
    main()
