"""The eval harness itself is code — it gets tested like everything else."""

from pathlib import Path

from filingsdesk.ingestion.filings import load_fixture_filings
from filingsdesk.ingestion.service import ingest_filings, run_ingestion
from filingsdesk.rag.evals import compare_chunking, load_dataset, run_evals

DATASET = Path(__file__).resolve().parents[2] / "evals" / "dataset.jsonl"


def test_dataset_shape():
    cases = load_dataset(DATASET)
    answerable = [c for c in cases if not c.expect_refusal]
    probes = [c for c in cases if c.expect_refusal]
    assert len(answerable) == 25
    assert len(probes) == 5
    assert all(c.expected_keywords and c.source_accession for c in answerable)


def test_eval_metrics_meet_ci_thresholds(db_session):
    ingest_filings(db_session, load_fixture_filings())
    db_session.commit()

    report = run_evals(db_session, load_dataset(DATASET))
    assert report.retrieval_hit_rate >= 0.8  # CI gate
    assert report.faithfulness >= 0.9  # CI gate
    assert report.keyword_recall >= 0.8  # tracked, not gated
    assert report.refusal_accuracy >= 0.6  # lexical embedder: honest floor
    assert report.n_answerable == 25


def test_compare_chunking_reports_both_strategies():
    rates = compare_chunking(load_dataset(DATASET))
    assert set(rates) == {"fixed", "section"}
    assert all(rate >= 0.9 for rate in rates.values())


def test_run_ingestion_fixtures_end_to_end(db_session):
    totals = run_ingestion(symbols=["AAPL", "MSFT"], fixtures=True)
    assert totals["prices"] == 1000  # 2 symbols × 500 fixture bars
    assert totals["filings"] == 5

    totals_again = run_ingestion(symbols=["AAPL", "MSFT"], fixtures=True)
    assert totals_again["filings"] == 0  # idempotent re-run
