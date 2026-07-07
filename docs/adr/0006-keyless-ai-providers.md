# ADR-0006: Keyless-by-default AI providers (pluggable embedder + answerer)

**Status:** accepted · 2026-07-07

## Problem
The RAG layer needs embeddings and answer generation. Cloud APIs (OpenAI/Anthropic/Voyage)
need keys and money; CI must run the eval harness on every push, deterministically, for
free; and reviewers should be able to `docker compose up` without any secrets.

## Options
1. Hard-depend on a cloud embedding + LLM API — best quality, but CI evals become flaky,
   non-deterministic, and cost-bearing; the demo dies without a key.
2. Bundle a local model (sentence-transformers) — keyless but drags in ~2 GB of torch,
   slow CI, heavyweight images.
3. **Pluggable providers with a deterministic local default** — a hashed-n-gram embedder
   (384-dim, pure NumPy, deterministic) and an extractive answerer (returns the most
   relevant retrieved sentences verbatim, with citations). Cloud providers slot in via
   config when keys exist.

## Decision
Option 3. `Embedder` and `Answerer` are protocols; defaults are `HashingEmbedder` and
`ExtractiveAnswerer`. The eval harness runs against the defaults in CI — deterministic
thresholds, no secrets. Setting `EMBEDDING_PROVIDER` / `ANSWER_PROVIDER` + keys upgrades
quality without touching the pipeline. Guardrails (out-of-corpus refusal via similarity
floor, low-confidence flagging, prompt-injection screening on document text) live in the
pipeline, not the provider, so they apply to any backend.

## Trade-offs
Hashed n-gram embeddings are lexical, not semantic — synonyms don't match. Retrieval
quality is honestly lower than a cloud embedder; the eval report says which provider
produced the published numbers. Extractive answers can read stilted, but they cannot
hallucinate: every sentence is a quote with a citation. For a system whose selling point
is *grounded* answers, that is the right default failure mode.
