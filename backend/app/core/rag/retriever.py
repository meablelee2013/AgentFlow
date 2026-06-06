"""
Hybrid retriever — combines vector similarity + keyword (BM25) search.

Architecture:
    Query → Embedding + Keyword Extraction
           ├── Vector search (pgvector cosine similarity)
           └── Keyword search (PostgreSQL full-text search)
           ↓
    Fusion (weighted Reciprocal Rank Fusion)
           ↓
    Top-K results
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rag.embedder import Embedder


class HybridRetriever:
    """Hybrid retrieval: vector similarity + keyword matching.

    Usage:
        retriever = HybridRetriever(db_session)
        results = await retriever.search("What is LangGraph?", top_k=5)
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedder = Embedder()

    async def search(
        self,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.7,
        knowledge_base_id: str | None = None,
    ) -> list[dict]:
        """Hybrid search combining vector and keyword results.

        Args:
            query: Search query string
            top_k: Number of results to return
            vector_weight: Weight for vector similarity (0-1), remainder for BM25
            knowledge_base_id: Optional filter by knowledge base

        Returns:
            List of {content, source, score, chunk_index} dicts
        """
        # 1. Vector search
        query_embedding = await self.embedder.embed_single(query)
        vector_results = await self._vector_search(query_embedding, top_k * 2, knowledge_base_id)

        # 2. Keyword search (PostgreSQL full-text)
        keyword_results = await self._keyword_search(query, top_k * 2, knowledge_base_id)

        # 3. Reciprocal Rank Fusion
        fused = self._rrf_fusion(vector_results, keyword_results, vector_weight)
        return fused[:top_k]

    async def _vector_search(
        self, embedding: list[float], top_k: int, knowledge_base_id: str | None
    ) -> list[dict]:
        """Cosine similarity search via pgvector."""
        kb_filter = ""
        params = {"embedding": embedding, "top_k": top_k}

        if knowledge_base_id:
            kb_filter = """
                JOIN documents d ON dc.document_id = d.id
                WHERE d.knowledge_base_id = CAST(:kb_id AS uuid)
            """
            params["kb_id"] = knowledge_base_id
            where_clause = "AND d.knowledge_base_id = CAST(:kb_id AS uuid)"
        else:
            where_clause = ""

        query_sql = f"""
            SELECT dc.content, dc.chunk_index, dc.chunk_metadata,
                   1 - (dc.embedding <=> CAST(:embedding AS vector)) AS similarity
            FROM document_chunks dc
            JOIN documents d ON dc.document_id = d.id
            WHERE dc.embedding IS NOT NULL {where_clause}
            ORDER BY dc.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
        """

        result = await self.db.execute(text(query_sql), params)
        return [
            {
                "content": row[0],
                "chunk_index": row[1],
                "metadata": row[2],
                "score": float(row[3]),
                "source": "vector",
            }
            for row in result
        ]

    async def _keyword_search(
        self, query: str, top_k: int, knowledge_base_id: str | None
    ) -> list[dict]:
        """PostgreSQL full-text search."""
        kb_join = ""
        kb_where = ""
        if knowledge_base_id:
            kb_join = "JOIN documents d ON dc.document_id = d.id"
            kb_where = "AND d.knowledge_base_id = CAST(:kb_id AS uuid)"

        query_sql = f"""
            SELECT dc.content, dc.chunk_index, dc.chunk_metadata,
                   ts_rank(
                       to_tsvector('english', dc.content),
                       plainto_tsquery('english', :query)
                   ) AS rank
            FROM document_chunks dc
            {kb_join}
            WHERE to_tsvector('english', dc.content) @@ plainto_tsquery('english', :query)
            {kb_where}
            ORDER BY rank DESC
            LIMIT :top_k
        """

        params = {"query": query, "top_k": top_k}
        if knowledge_base_id:
            params["kb_id"] = knowledge_base_id

        result = await self.db.execute(text(query_sql), params)
        return [
            {
                "content": row[0],
                "chunk_index": row[1],
                "metadata": row[2],
                "score": float(row[3]),
                "source": "keyword",
            }
            for row in result
        ]

    def _rrf_fusion(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        vector_weight: float,
        k: int = 60,  # RRF smoothing constant
    ) -> list[dict]:
        """Reciprocal Rank Fusion — merge two ranked lists."""
        scores: dict[str, dict] = {}  # content_hash -> aggregated result

        # Score from vector rank
        for rank, item in enumerate(vector_results):
            key = item["content"][:100]  # Use content prefix as key
            rrf_score = vector_weight / (k + rank + 1)
            scores[key] = {
                "content": item["content"],
                "chunk_index": item["chunk_index"],
                "metadata": item["metadata"],
                "score": rrf_score,
            }

        # Score from keyword rank
        kw_weight = 1.0 - vector_weight
        for rank, item in enumerate(keyword_results):
            key = item["content"][:100]
            rrf_score = kw_weight / (k + rank + 1)
            if key in scores:
                scores[key]["score"] += rrf_score
            else:
                scores[key] = {
                    "content": item["content"],
                    "chunk_index": item["chunk_index"],
                    "metadata": item["metadata"],
                    "score": rrf_score,
                }

        # Sort by fused score descending
        return sorted(scores.values(), key=lambda x: x["score"], reverse=True)
