"""Guardrails applied to the RAG pipeline regardless of provider (ADR-0006).

- Confidence tiers from retrieval similarity: refuse / low-confidence / ok.
- Prompt-injection screening of *document* content: filings are untrusted input; text
  that addresses the assistant rather than describing the business is quarantined.
"""

import re
from enum import StrEnum

INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore (all |any )?(previous|prior|above) (instructions|context)",
        r"disregard (your|the) (instructions|system prompt|guidelines)",
        r"you are now\b",
        r"system prompt",
        r"\bas an ai\b.{0,40}\b(must|should) (obey|comply)",
        r"reveal (your|the) (instructions|prompt|secrets)",
        r"</?(system|assistant|instruction)>",
        r"BEGIN (NEW )?INSTRUCTIONS",
    )
]


class Confidence(StrEnum):
    REFUSE = "refuse"
    LOW = "low"
    OK = "ok"


def screen_for_injection(text: str) -> list[str]:
    """Return the list of suspicious patterns found in document text."""
    return [pattern.pattern for pattern in INJECTION_PATTERNS if pattern.search(text)]


def assess_confidence(
    top_similarity: float | None, refusal_floor: float, confidence_floor: float
) -> Confidence:
    if top_similarity is None or top_similarity < refusal_floor:
        return Confidence.REFUSE
    if top_similarity < confidence_floor:
        return Confidence.LOW
    return Confidence.OK
