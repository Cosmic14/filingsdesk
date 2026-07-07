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
and let the **eval harness decide**: the harness reports retrieval hit-rate per chunking
strategy. Default is section-aware (with fixed-size re-splitting of oversized sections and
sentence-boundary overlap), which won on the fixture corpus — see eval results in README.
Every chunk keeps `(filing_id, section, chunk_index)` so answers can cite their source.

## Trade-offs
Section detection is heuristic (regex on ITEM headings) and will mis-split unusual
filings; the fixed-size re-split bounds the damage. Carrying two strategies costs a little
code but turns a hand-wave ("we chunk by section") into a measured decision.
