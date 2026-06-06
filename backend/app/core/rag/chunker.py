"""
Document chunking strategies for RAG pipeline.

Chunking methods:
    - fixed_size: Split by character count with overlap
    - recursive: Split by natural separators (\n\n, \n, ., etc.)
    - semantic: LLM-powered semantic boundary detection (Phase 2)
"""

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """A single document chunk with metadata for citation."""
    content: str
    index: int
    source: str          # filename
    page: int | None = None
    metadata: dict | None = None


class DocumentChunker:
    """Document chunking with pluggable strategies.

    Usage:
        chunker = DocumentChunker(strategy="recursive", chunk_size=1000, overlap=200)
        chunks = chunker.split(text, source="doc.pdf")
    """

    def __init__(
        self,
        strategy: str = "recursive",
        chunk_size: int = 1000,
        overlap: int = 200,
    ):
        self.strategy = strategy
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str, *, source: str = "") -> list[Chunk]:
        """Split text into chunks using the configured strategy."""
        if self.strategy == "fixed_size":
            return self._fixed_size_split(text, source)
        elif self.strategy == "recursive":
            return self._recursive_split(text, source)
        else:
            raise ValueError(f"Unknown chunking strategy: {self.strategy}")

    def _fixed_size_split(self, text: str, source: str) -> list[Chunk]:
        """Split by fixed character count with overlap."""
        chunks = []
        start = 0
        idx = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            chunk_text = text[start:end]
            if chunk_text.strip():
                chunks.append(Chunk(
                    content=chunk_text.strip(),
                    index=idx,
                    source=source,
                ))
                idx += 1
            if end >= text_len:
                break
            start = end - self.overlap
            if start <= 0 or start >= end:
                start = end
        return chunks

    def _recursive_split(self, text: str, source: str) -> list[Chunk]:
        """Split recursively by natural separators.

        Priority: paragraph (\n\n) > line (\n) > sentence (.!?) > character
        """
        separators = ["\n\n", "\n", ". ", "! ", "? ", ".", "!", "?", " "]
        return self._recursive_chunk(text, separators, source)

    def _recursive_chunk(
        self, text: str, separators: list[str], source: str, idx: int = 0
    ) -> list[Chunk]:
        """Recursively split text using separators in priority order."""
        if not text.strip():
            return []

        # If text fits in one chunk, return it
        if len(text) <= self.chunk_size:
            return [Chunk(content=text.strip(), index=idx, source=source)]

        # Try splitting by the first available separator
        sep = separators[0] if separators else None
        if sep is None:
            # Fallback: hard cut
            return self._fixed_size_split(text, source)

        splits = text.split(sep)
        if len(splits) == 1:
            # Separator not found, try next one
            return self._recursive_chunk(text, separators[1:], source, idx)

        # Merge splits into chunks that fit chunk_size
        chunks = []
        current = ""
        for part in splits:
            candidate = (current + sep + part).strip() if current else part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(Chunk(content=current.strip(), index=idx, source=source))
                    idx += 1
                # If the part itself is too large, recurse
                if len(part) > self.chunk_size:
                    sub = self._recursive_chunk(part, separators[1:], source, idx)
                    chunks.extend(sub)
                    idx += len(sub)
                    current = ""
                else:
                    current = part

        if current.strip():
            chunks.append(Chunk(content=current.strip(), index=idx, source=source))

        return chunks
