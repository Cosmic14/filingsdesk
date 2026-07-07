# ADR-0005: Section-aware chunking, measured against fixed-size

**Status:** accepted · 2026-07-07

## Problem
Filings must be split into chunks for embedding and retrieval. Chunk boundaries drive
retrieval quality: too small loses context, too big dilutes the embedding and blows the
answer context.

## Options
1. **Fixed-size** — N characters/tokens with overlap. Simple, uniform, ignores structure.
2. **Section-aware** — split on filing structure (ITEM headings, paragraph boundaries),
   then re-split oversized sections with overlap. Chunks align with how humans cite
   filings ("Item 1A — Risk Factors").
3. Semantic chunking (embedding-similarity boundaries) — highest cost/complexity; needs an
   embedder in the loop during ingestion.

## Decision
Implement **both** fixed-size and section-aware behind one interface, choose per config,
and let the **eval harness decide**: `filingsdesk-evals --compare-chunking` reports
retrieval hit-rate per strategy. Measured on the fixture corpus (top-5): tied at 1.00 at
the default 1600-char size; at 300-char chunks section-aware keeps 1.00 while fixed drops
to 0.96 by splitting facts across windows. Default is section-aware — it never scored
worse, and its chunks carry `(filing_id, section, chunk_index)` labels, which makes
citations human-meaningful ("Item 1A — Risk Factors") rather than byte offsets.

## Trade-offs
Section detection is heuristic (regex on ITEM headings) and will mis-split unusual
filings; the fixed-size re-split bounds the damage. Carrying two strategies costs a little
code but turns a hand-wave ("we chunk by section") into a measured decision.
