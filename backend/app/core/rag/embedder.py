"""
Embedding manager — pure Python TF-IDF (zero external dependencies).

Phase 1: Pure Python TF-IDF for MVP (fast, offline).
Phase 2: Upgrade to sentence-transformers or API embeddings.
"""

import asyncio
import math
from collections import Counter

from app.config import settings


class Embedder:
    """Text embedding using pure Python TF-IDF (384-dim output)."""

    def __init__(self):
        self.dimension = settings.VECTOR_DIMENSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate TF-IDF embeddings for a list of texts.

        Uses a simple bag-of-words TF-IDF with the top-N terms
        across the batch as the feature space.
        """
        if not texts:
            return []

        # Build vocabulary from top terms across all texts
        word_counts = Counter()
        doc_freqs = Counter()
        for text in texts:
            words = self._tokenize(text)
            word_counts.update(words)
            doc_freqs.update(set(words))

        # Select top terms as features
        vocab = [w for w, _ in word_counts.most_common(self.dimension)]
        if not vocab:
            return [[0.0] * self.dimension for _ in texts]

        # Build TF-IDF vectors
        N = len(texts)
        idx = {w: i for i, w in enumerate(vocab)}
        vectors = []
        for text in texts:
            words = self._tokenize(text)
            tf = Counter(words)
            vec = [0.0] * self.dimension
            for word, count in tf.items():
                if word in idx:
                    df = doc_freqs.get(word, 1)
                    vec[idx[word]] = (count / max(len(words), 1)) * math.log(N / (df + 1) + 1)
            vectors.append(vec)
        return vectors

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed([text])
        return results[0]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple English tokenization."""
        import re
        return re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
