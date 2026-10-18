# ADR-0008: Retrieval that holds up on real SEC filings

**Status:** accepted · 2026-10-18

## Problem
On the bundled fixtures every metric was green. On real filings (15 EDGAR documents for
AAPL, MSFT, NVDA, AMZN, GOOGL: ~2,600 chunks) it fell apart:
- The extractive answerer quoted run-together table text ("...2026.Rest of Asia...") and
  answered "What is the capital of France?" with balance-sheet lines.
- With Claude answering, 3 of 6 real questions were refused although the answer was in the
  corpus: the lexical hashing embedder's top 5 never reached the right chunks.
- With a small semantic model alone, every NVIDIA chunk scored 0.73-0.76, so "How many
  employees does NVIDIA have?" never surfaced the Human Capital section.

## Decision
1. **Cleaner text.** Line breaks at block elements, `|` between table cells, the hidden
   inline-XBRL header skipped. "ITEM 1A" lines survive, so section-aware chunking works
   (10-47 sections per filing instead of run-on text).
2. **The right filings.** Latest 10-K plus the two latest 10-Qs per company, not "any 3".
3. **Company-aware retrieval.** Registrant names come from EDGAR's ticker file; a question
   naming a company (name, ticker or alias) searches only that company's filings.
4. **Local semantic embeddings.** `EMBEDDING_PROVIDER=fastembed` (BAAI bge-small-en-v1.5,
   ONNX, 384-dim, no key, no torch), with bge's separate query/passage modes. The keyless
   hashing embedder stays the default, so CI is unchanged and deterministic.
5. **Hybrid search.** Postgres full-text search (generated `tsvector` + GIN, migration 0003)
   fused with dense cosine by reciprocal rank fusion (k=60). Inside one company's filings
   the company name is stripped from the keyword query, because "NVIDIA" matches every
   NVIDIA chunk and drowned out "employees".

## Measured (local, Claude Opus 5.5 answering, `scripts/live_smoke.py`)
| setup | real questions behaving correctly |
|---|---|
| hashing embedder, no company filter | 3 / 6 (3 false refusals) |
| + company filter + fastembed | 7 / 9 |
| + hybrid search (company-stripped keywords) | **10 / 10** |

Fixture evals in CI are unchanged: hit rate 1.00, faithfulness 1.00.

## Trade-offs
Embedding 2,600 chunks with fastembed takes ~4 minutes on a laptop CPU; queries take
~4-6 s end to end (most of it the Claude call). Vectors from different embedding providers
must not share a database, so the live stack uses its own volume. Real figures change every
quarter, so the live smoke test checks behaviour (answered with citations, refused when it
should be), not exact numbers.
