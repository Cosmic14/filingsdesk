"""HashingEmbedder: determinism, normalisation, and lexical similarity ordering."""

import numpy as np

from filingsdesk.rag.embeddings import HashingEmbedder


def test_deterministic_across_instances():
    a = HashingEmbedder(dim=384).embed(["Apple services revenue grew 12 percent"])
    b = HashingEmbedder(dim=384).embed(["Apple services revenue grew 12 percent"])
    np.testing.assert_array_equal(a, b)


def test_unit_norm():
    vecs = HashingEmbedder(dim=384).embed(["some text here", "other words entirely"])
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), [1.0, 1.0], rtol=1e-5)


def test_empty_text_is_zero_vector_not_nan():
    vec = HashingEmbedder(dim=64).embed([""])[0]
    assert not np.isnan(vec).any()
    assert np.linalg.norm(vec) == 0.0


def test_similar_text_scores_higher_than_unrelated():
    embedder = HashingEmbedder(dim=384)
    query, related, unrelated = embedder.embed(
        [
            "What was Azure cloud revenue growth?",
            "Azure and other cloud services revenue grew 29 percent year over year",
            "The quick brown fox jumps over the lazy dog near the river bank",
        ]
    )
    assert query @ related > query @ unrelated


def test_shape_matches_dim():
    assert HashingEmbedder(dim=128).embed(["a", "b", "c"]).shape == (3, 128)
