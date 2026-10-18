"""RAG eval harness (run in CI): retrieval hit rate, faithfulness, keyword recall,
refusal accuracy — plus an in-memory chunking-strategy comparison for ADR-0005.

Faithfulness here is checkable, not vibes: every piece of evidence behind an answer must
appear verbatim in an ingested filing body. For the extractive answerer the evidence is
the answer itself, so it scores 1.0 by construction; for Claude it is the quote behind
each claim. Run with ANSWER_PROVIDER=claude to evaluate Claude; token totals and latency
are printed alongside the scores.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from filingsdesk.db import Filing
from filingsdesk.db.session import session_scope
from filingsdesk.rag.answer import answer_question
from filingsdesk.rag.companies import detect_companies
from filingsdesk.rag.retrieval import retrieve

WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_keywords: tuple[str, ...] = ()
    source_accession: str | None = None
    expect_refusal: bool = False


@dataclass
class EvalReport:
    retrieval_hit_rate: float = 0.0
    faithfulness: float = 0.0
    keyword_recall: float = 0.0
    refusal_accuracy: float = 0.0
    n_answerable: int = 0
    n_refusal_probes: int = 0
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "retrieval_hit_rate": round(self.retrieval_hit_rate, 4),
            "faithfulness": round(self.faithfulness, 4),
            "keyword_recall": round(self.keyword_recall, 4),
            "refusal_accuracy": round(self.refusal_accuracy, 4),
            "n_answerable": self.n_answerable,
            "n_refusal_probes": self.n_refusal_probes,
            "failures": self.failures,
        }


def load_dataset(path: Path) -> list[EvalCase]:
    cases = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cases.append(
            EvalCase(
                question=row["question"],
                expected_keywords=tuple(row.get("expected_keywords", ())),
                source_accession=row.get("source_accession"),
                expect_refusal=row.get("expect_refusal", False),
            )
        )
    return cases


def run_evals(session: Session, cases: list[EvalCase], top_k: int = 5) -> EvalReport:
    squashed = [WHITESPACE_RE.sub(" ", body) for body in session.scalars(select(Filing.body))]
    report = EvalReport()
    hits = faithful = keyword_hits = refusals_correct = 0

    for case in cases:
        if case.expect_refusal:
            report.n_refusal_probes += 1
            result = answer_question(session, case.question, top_k=top_k)
            if result.refused:
                refusals_correct += 1
            else:
                report.failures.append(f"not refused: {case.question}")
            continue

        report.n_answerable += 1

        symbols, keyword_query = detect_companies(session, case.question)
        retrieved = retrieve(session, case.question, top_k, symbols or None, keyword_query)
        if any(chunk.accession_no == case.source_accession for chunk in retrieved):
            hits += 1
        else:
            report.failures.append(f"retrieval miss: {case.question}")

        result = answer_question(session, case.question, top_k=top_k)
        if not result.refused:
            evidence = [WHITESPACE_RE.sub(" ", e).strip() for e in result.evidence]
            if evidence and all(any(e in body for body in squashed) for e in evidence):
                faithful += 1
            else:
                report.failures.append(f"unfaithful answer: {case.question}")
            if any(kw.lower() in result.answer.lower() for kw in case.expected_keywords):
                keyword_hits += 1
            else:
                report.failures.append(f"keywords missing: {case.question}")
        else:
            report.failures.append(f"wrongly refused: {case.question}")

    if report.n_answerable:
        report.retrieval_hit_rate = hits / report.n_answerable
        report.faithfulness = faithful / report.n_answerable
        report.keyword_recall = keyword_hits / report.n_answerable
    if report.n_refusal_probes:
        report.refusal_accuracy = refusals_correct / report.n_refusal_probes
    return report


def compare_chunking(cases: list[EvalCase], top_k: int = 5) -> dict[str, float]:
    """ADR-0005 evidence: retrieval hit rate per chunking strategy, in memory (no DB)."""
    import numpy as np

    from filingsdesk.config import get_settings
    from filingsdesk.ingestion.filings import load_fixture_filings
    from filingsdesk.rag.chunking import chunk_filing_text
    from filingsdesk.rag.embeddings import get_embedder

    settings = get_settings()
    answerable = [case for case in cases if not case.expect_refusal]
    results = {}
    for strategy in ("fixed", "section"):
        corpus: list[tuple[str, str]] = []  # (accession, chunk text)
        for record in load_fixture_filings():
            for chunk in chunk_filing_text(
                record.body,
                strategy=strategy,
                chunk_size=settings.chunk_size_chars,
                overlap=settings.chunk_overlap_chars,
            ):
                corpus.append((record.accession_no, chunk.text))
        matrix = get_embedder().embed([text for _, text in corpus])
        hits = 0
        for case in answerable:
            query = get_embedder().embed([case.question])[0]
            order = np.argsort(-(matrix @ query))[:top_k]
            if any(corpus[i][0] == case.source_accession for i in order):
                hits += 1
        results[strategy] = hits / len(answerable)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG evals against the ingested corpus")
    parser.add_argument("--dataset", type=Path, default=Path("evals/dataset.jsonl"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-hit-rate", type=float, default=None)
    parser.add_argument("--min-faithfulness", type=float, default=None)
    parser.add_argument("--compare-chunking", action="store_true")
    args = parser.parse_args()

    cases = load_dataset(args.dataset)

    if args.compare_chunking:
        rates = compare_chunking(cases, args.top_k)
        print(json.dumps({f"hit_rate_{k}": round(v, 4) for k, v in rates.items()}, indent=2))
        return

    with session_scope() as session:
        report = run_evals(session, cases, args.top_k)

    print(json.dumps(report.as_dict(), indent=2))

    from filingsdesk.rag.claude_answerer import TALLY

    if TALLY.calls:
        latencies = sorted(TALLY.latencies)
        usage = {
            "claude_calls": TALLY.calls,
            **{f"total_{kind}": count for kind, count in TALLY.tokens.items()},
            "mean_latency_s": round(sum(latencies) / len(latencies), 2),
            "p95_latency_s": round(latencies[int(0.95 * (len(latencies) - 1))], 2),
        }
        print(json.dumps(usage, indent=2))

    ok = True
    if args.min_hit_rate is not None and report.retrieval_hit_rate < args.min_hit_rate:
        print(f"FAIL hit rate {report.retrieval_hit_rate:.2%} < {args.min_hit_rate:.2%}")
        ok = False
    if args.min_faithfulness is not None and report.faithfulness < args.min_faithfulness:
        print(f"FAIL faithfulness {report.faithfulness:.2%} < {args.min_faithfulness:.2%}")
        ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
