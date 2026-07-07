"""Filing chunkers (ADR-0005): fixed-size and section-aware behind one entry point.

Section-aware splits on the standard `ITEM N.` headings of SEC filings, then re-splits
oversized sections with the fixed-size chunker so no chunk exceeds `chunk_size`. Every
chunk carries its section label for citations.
"""

import re
from dataclasses import dataclass

SECTION_RE = re.compile(r"^\s*ITEM\s+\d+[A-Z]?\.[^\n]*", re.MULTILINE | re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    text: str
    section: str | None = None


def chunk_fixed(
    text: str, chunk_size: int, overlap: int, section: str | None = None
) -> list[Chunk]:
    """Sliding window with overlap; window ends snap back to the last whitespace."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")

    text = text.strip()
    if not text:
        return []

    chunks: list[Chunk] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary != -1:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            chunks.append(Chunk(text=piece, section=section))
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_section_aware(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return chunk_fixed(text, chunk_size, overlap)

    chunks: list[Chunk] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        chunks.extend(chunk_fixed(preamble, chunk_size, overlap, section="PREAMBLE"))

    for i, match in enumerate(matches):
        label = re.sub(r"\s+", " ", match.group().strip())[:120]
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[match.start() : body_end].strip()
        if len(body) <= chunk_size:
            chunks.append(Chunk(text=body, section=label))
        else:
            chunks.extend(chunk_fixed(body, chunk_size, overlap, section=label))
    return chunks


def chunk_filing_text(
    text: str, strategy: str = "section", chunk_size: int = 1600, overlap: int = 200
) -> list[Chunk]:
    if strategy == "section":
        return chunk_section_aware(text, chunk_size, overlap)
    if strategy == "fixed":
        return chunk_fixed(text, chunk_size, overlap)
    raise ValueError(f"unknown chunking strategy: {strategy!r}")
