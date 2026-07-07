"""Chunking behaviour (ADR-0005): windows, overlap, section detection."""

import pytest

from filingsdesk.rag.chunking import chunk_filing_text, chunk_fixed, chunk_section_aware

FILING_TEXT = """Preamble text about the company.

ITEM 1. BUSINESS

We design and sell widgets across three segments. Revenue grew nicely this year.

ITEM 1A. RISK FACTORS

Our supply chain is concentrated. Regulation could hurt us badly some day.

ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS

Gross margin expanded on mix shift toward services and subscriptions.
"""


def test_fixed_chunks_respect_size_and_cover_text():
    text = "word " * 500  # 2500 chars
    chunks = chunk_fixed(text, chunk_size=400, overlap=50)
    assert all(len(chunk.text) <= 400 for chunk in chunks)
    assert len(chunks) >= 6
    reassembled = " ".join(chunk.text for chunk in chunks)
    assert reassembled.count("word") >= 500  # overlap duplicates, never loses


def test_fixed_chunk_overlap_repeats_content():
    text = " ".join(f"tok{i}" for i in range(200))
    chunks = chunk_fixed(text, chunk_size=300, overlap=100)
    for first, second in zip(chunks, chunks[1:], strict=False):
        tail = first.text[-80:].split()[1:-1]
        assert any(token in second.text for token in tail)


def test_fixed_rejects_bad_params():
    with pytest.raises(ValueError):
        chunk_fixed("x", chunk_size=0, overlap=0)
    with pytest.raises(ValueError):
        chunk_fixed("x", chunk_size=100, overlap=100)


def test_fixed_empty_text_gives_no_chunks():
    assert chunk_fixed("   ", chunk_size=100, overlap=10) == []


def test_section_aware_labels_sections():
    chunks = chunk_section_aware(FILING_TEXT, chunk_size=1600, overlap=200)
    sections = [chunk.section for chunk in chunks]
    assert sections[0] == "PREAMBLE"
    assert any(s and s.startswith("ITEM 1.") for s in sections)
    assert any(s and s.startswith("ITEM 1A.") for s in sections)
    assert any(s and s.startswith("ITEM 7.") for s in sections)


def test_section_aware_resplits_oversized_sections():
    big_section = "ITEM 1. BUSINESS\n\n" + ("blah " * 1000)
    chunks = chunk_section_aware(big_section, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert all(chunk.section and chunk.section.startswith("ITEM 1.") for chunk in chunks)


def test_section_aware_falls_back_when_no_headings():
    chunks = chunk_section_aware("Just a plain document with no items.", 1600, 200)
    assert len(chunks) == 1
    assert chunks[0].section is None


def test_entry_point_selects_strategy():
    assert chunk_filing_text(FILING_TEXT, strategy="section")[0].section == "PREAMBLE"
    assert chunk_filing_text(FILING_TEXT, strategy="fixed")[0].section is None
    with pytest.raises(ValueError, match="unknown chunking strategy"):
        chunk_filing_text(FILING_TEXT, strategy="semantic")
