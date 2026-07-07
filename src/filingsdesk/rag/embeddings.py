"""Pluggable embedders (ADR-0006). Default is deterministic and keyless.

`HashingEmbedder` hashes word unigrams/bigrams and character trigrams into a fixed-size
signed vector (the classic hashing trick), L2-normalised so dot product = cosine
similarity. Lexical rather than semantic — the honest trade-off is documented in the ADR.
"""

import hashlib
import re
from typing import Protocol

import numpy as np

from filingsdesk.config import get_settings

TOKEN_RE = re.compile(r"[a-z0-9]+")

# Function words carry no retrieval signal but match every document, inflating the
# similarity of unrelated questions and blunting the out-of-corpus refusal guardrail.
STOPWORDS = frozenset(
    "a an and are as at be by did do does for from had has have how i in is it its of on or "
    "our s t that the their this to was we were what when where which who why will with you".split()
)


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _stable_hash(token: str) -> int:
    return int.from_bytes(hashlib.md5(token.encode()).digest()[:8], "little")


class HashingEmbedder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    @staticmethod
    def _stem(word: str) -> str:
        """Plural folding only — enough to match 'risks'↔'risk' without a stemmer dep."""
        if len(word) > 3 and word.endswith("es"):
            return word[:-2]
        if len(word) > 2 and word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    def _features(self, text: str) -> list[str]:
        words = [
            self._stem(w) for w in TOKEN_RE.findall(text.lower()) if w not in STOPWORDS
        ]
        bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:], strict=False)]
        # Char trigrams give partial-match robustness (plurals, inflections) but only
        # for substantive words — short-word trigrams are pure cross-document noise.
        trigrams = [w[i : i + 3] for w in words if len(w) >= 5 for i in range(len(w) - 2)]
        return words + bigrams + trigrams

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                h = _stable_hash(feature)
                index = h % self.dim
                sign = 1.0 if (h >> 63) & 1 else -1.0
                vectors[row, index] += sign
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vectors / norms


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Default embedder for the configured dimension. Cloud providers slot in here."""
    global _embedder
    if _embedder is None:
        _embedder = HashingEmbedder(dim=get_settings().embedding_dim)
    return _embedder
