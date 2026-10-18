# ADR-0007: Claude answerer — the model writes, code verifies

**Status:** accepted · 2026-10-18

## Problem
The extractive answerer (ADR-0006) can't hallucinate, but it reads stiffly, pads answers
with loosely related sentences, and inherits the lexical embedder's blind spots: the eval
showed 0.92 keyword recall and 0.80 refusal accuracy ("capital of France" retrieves
capital-expenditure text and gets answered). A generative answerer reads better and can
judge relevance, but it can also invent facts, which is unacceptable for filings.

## Decision
`ANSWER_PROVIDER=claude` adds a Claude answerer behind the existing pipeline:

1. **Deterministic gates first.** Retrieval, prompt-injection quarantine and the
   similarity refusal floor run before any API call, so obvious misses cost nothing.
2. **Structured output.** Claude gets the retrieved chunks as numbered `<source>` blocks
   (marked untrusted, closing tags broken) and must return JSON matching a strict schema:
   `answerable` plus up to four claims, each with a source number and a verbatim quote.
3. **Code verifies every claim.** A claim is shown only if its quote appears in the cited
   source (whitespace-normalised, at least 12 characters). The answer is built from
   verified claims only; any dropped claim downgrades confidence to `low`.
4. **Fail safe.** Timeouts, API errors, `max_tokens` truncation, refusals or schema
   violations fall back to the extractive answer, like the cache falling back to memory
   (ADR-0002). The SDK retries 429/5xx twice with backoff; the timeout is 30 s.
5. **Cost and latency controls.** Frozen system prompt first with `cache_control`, so the
   prefix is cached; `effort: low`; `max_tokens` capped; server-side refusal fallback
   (`fallbacks: "default"`) on. Tokens by kind, latency and outcomes go to Prometheus,
   plus one structured log line per call with the request ID.

CI keeps running the keyless extractive path (ADR-0006 still holds); the Claude run is a
manual `ANSWER_PROVIDER=claude filingsdesk-evals` with a key.

## Measured (2026-10-18, Opus 5.5, effort low, same 30-case eval)

| metric | extractive | claude |
|---|---|---|
| retrieval hit rate | 1.00 | 1.00 |
| faithfulness (every quote verbatim in a filing) | 1.00 | 1.00, 0 claims dropped |
| keyword recall | 0.92 | 1.00 |
| refusal accuracy | 0.80 | 1.00 |
| mean / p95 latency | — | 2.95 s / 3.51 s |

26 API calls: the refusal floor stopped 4 of the 5 out-of-corpus probes before the API.
Per call: ~1,360 uncached input tokens, 587 cached (system prompt + schema; every call
was a cache hit), ~180 output tokens. At $4 / $20 / $0.20 per MTok (input / output /
cache read) that is **~$0.009 per answer**; caching cut the bill by ~20%.

## Trade-offs
The quote check proves the source *says* something; it doesn't prove the paraphrase is
faithful to it. That residual risk is covered by the eval set and spot checks, and an
LLM-as-judge pass would be the next step at scale. Answers now cost money and ~3 s, so
the deterministic gates in front of the model matter more, not less.
