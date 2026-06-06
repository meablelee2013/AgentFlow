"""Embedding manager — generates and stores vector embeddings via pgvector."""
import os
from app.config import settings
from openai import AsyncOpenAI


class Embedder:
    """Generates embeddings using DeepSeek / OpenAI-compatible API.

    Usage:
        embedder = Embedder()
        vectors = await embedder.embed(["text chunk 1", "text chunk 2"])
        # Store vectors in pgvector via DocumentChunk model
    """

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY"),
            base_url=settings.DEEPSEEK_BASE_URL,
        )
        self.dimension = settings.VECTOR_DIMENSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        Uses DeepSeek embedding API (OpenAI-compatible).
        For production, consider batching to reduce API calls.
        """
        embeddings = []
        for text in texts:
            response = await self.client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text[:8000],  # Truncate to model limit
            )
            embeddings.append(response.data[0].embedding)
        return embeddings

    async def embed_single(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        results = await self.embed([text])
        return results[0]
