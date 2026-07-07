"""Integration test infrastructure: real Postgres, real migrations, clean tables.

DATABASE_URL defaults to the local test database; CI points it at the pgvector service
container. Everything here is marked `integration` and skipped when Postgres is down.
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg:///filingsdesk_test")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

import filingsdesk.rag.store as rag_store
from filingsdesk.config import get_settings
from filingsdesk.db import get_engine
from filingsdesk.db.session import _session_factory


def pytest_collection_modifyitems(items):
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def migrated_engine():
    get_settings.cache_clear()
    get_engine.cache_clear()
    _session_factory.cache_clear()
    engine = get_engine()
    try:
        with engine.connect():
            pass
    except Exception:
        pytest.skip("Postgres unavailable — skipping integration tests")
    command.upgrade(Config("alembic.ini"), "head")
    return engine


@pytest.fixture
def db_session(migrated_engine):
    """Fresh tables and a fresh vector-store singleton for every test."""
    with migrated_engine.begin() as conn:
        conn.execute(text("TRUNCATE filing_chunks, filings, prices, instruments CASCADE"))
    rag_store._store = None
    session = _session_factory()()
    yield session
    session.close()
