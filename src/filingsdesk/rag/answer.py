"""Answer generation with citations (ADR-0006).

Default answerer is extractive: it selects the retrieved sentences most similar to the
question and quotes them with numbered citations. It cannot hallucinate — every sentence
in the answer exists verbatim in a cited filing chunk. An LLM answerer can be slotted in
behind the same interface without touching guardrails or the API.
"""

import re
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy.orm import Session

from filingsdesk.config import get_settings
from filingsdesk.rag.embeddings import STOPWORDS, TOKEN_RE, get_embedder
from filingsdesk.rag.guardrails import Confidence, assess_confidence
from filingsdesk.rag.retrieval import RetrievedChunk, retrieve

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

REFUSAL_TEXT = (
    "I can't answer that from the filings in this corpus. "
    "The question appears to be outside the ingested documents."
)


@dataclass
class Citation:
    marker: int
    accession_no: str
    symbol: str | None
    form_type: str
    section: str | None
    similarity: float


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: str = Confidence.OK
    refused: bool = False
    injection_flagged: bool = False


def _best_sentences(
    question: str, chunks: list[RetrievedChunk], max_sentences: int
) -> tuple[list[tuple[str, RetrievedChunk]], float]:
    """Top sentences across retrieved chunks, plus the best sentence score — the
    confidence signal (chunk-level cosine is diluted by chunk length)."""
    candidates: list[tuple[str, RetrievedChunk]] = []
    for chunk in chunks:
        for sentence in SENTENCE_SPLIT_RE.split(chunk.text):
            sentence = sentence.strip()
            # Skip headings/fragments — they read poorly as quoted answer material.
            if len(sentence) >= 40 and not sentence.isupper():
                candidates.append((sentence, chunk))
    if not candidates:
        return [], 0.0
    embedder = get_embedder()
    question_vec = embedder.embed([question])[0]
    sentence_vecs = embedder.embed([sentence for sentence, _ in candidates])
    cosines = sentence_vecs @ question_vec
    # Pivoted length correction: pure cosine over-rewards very short sentences (one
    # matching token in a 4-token fragment beats a fact-dense sentence). Weight by a
    # saturating function of content-token count for *ranking*; confidence still uses
    # the raw cosine so guardrail floors keep a stable meaning.
    token_counts = np.array(
        [
            min(sum(1 for w in TOKEN_RE.findall(s.lower()) if w not in STOPWORDS), 30)
            for s, _ in candidates
        ]
    )
    scores = cosines * np.sqrt(token_counts)
    order = np.argsort(-scores)[:max_sentences]
    best = [candidates[i] for i in sorted(order)]  # keep document order for readability
    return best, float(cosines.max())


def answer_question(session: Session, question: str, top_k: int | None = None) -> AnswerResult:
    settings = get_settings()
    chunks = retrieve(session, question, top_k or settings.retrieval_top_k)

    # Quarantine chunks that try to address the assistant (prompt injection).
    flagged = [chunk for chunk in chunks if chunk.injection_flags]
    chunks = [chunk for chunk in chunks if not chunk.injection_flags]

    selected, best_sentence_score = _best_sentences(question, chunks, max_sentences=4)
    confidence = assess_confidence(
        best_sentence_score if selected else None,
        settings.similarity_refusal_floor,
        settings.similarity_confidence_floor,
    )
    if confidence is Confidence.REFUSE or not selected:
        return AnswerResult(
            answer=REFUSAL_TEXT,
            confidence=Confidence.REFUSE,
            refused=True,
            injection_flagged=bool(flagged),
        )

    citations: list[Citation] = []
    marker_by_chunk: dict[int, int] = {}
    parts: list[str] = []
    for sentence, chunk in selected:
        if chunk.chunk_id not in marker_by_chunk:
            marker = len(marker_by_chunk) + 1
            marker_by_chunk[chunk.chunk_id] = marker
            citations.append(
                Citation(
                    marker=marker,
                    accession_no=chunk.accession_no,
                    symbol=chunk.symbol,
                    form_type=chunk.form_type,
                    section=chunk.section,
                    similarity=round(chunk.similarity, 4),
                )
            )
        parts.append(f"{sentence} [{marker_by_chunk[chunk.chunk_id]}]")

    return AnswerResult(
        answer=" ".join(parts),
        citations=citations,
        confidence=confidence,
        refused=False,
        injection_flagged=bool(flagged),
    )
