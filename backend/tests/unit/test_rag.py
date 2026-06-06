"""Unit tests for RAG pipeline components"""
from app.core.rag.chunker import DocumentChunker, Chunk


def test_chunker_fixed_size():
    """Fixed-size chunking should respect chunk_size"""
    chunker = DocumentChunker(strategy="fixed_size", chunk_size=50, overlap=10)
    text = "ABCDEFGHIJ " * 20  # 220 chars → ~5 chunks
    chunks = chunker.split(text, source="test.txt")
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c.content) <= 50
        assert c.source == "test.txt"


def test_chunker_recursive():
    """Recursive chunking should split on natural boundaries"""
    chunker = DocumentChunker(strategy="recursive", chunk_size=200, overlap=50)
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = chunker.split(text, source="doc.pdf")
    assert len(chunks) >= 1
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.content.strip()


def test_chunker_single_short_text():
    """Short text should produce single chunk"""
    chunker = DocumentChunker(strategy="recursive", chunk_size=1000)
    chunks = chunker.split("Hi!", source="test.txt")
    assert len(chunks) == 1
    assert chunks[0].content == "Hi!"


def test_chunker_empty_text():
    """Empty text should produce no chunks"""
    chunker = DocumentChunker()
    chunks = chunker.split("", source="empty.txt")
    assert len(chunks) == 0


def test_chunker_invalid_strategy():
    """Unknown strategy should raise ValueError"""
    chunker = DocumentChunker(strategy="nonexistent")
    try:
        chunker.split("test", source="test.txt")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_chunk_dataclass():
    """Chunk dataclass should hold expected fields"""
    c = Chunk(content="Hello", index=0, source="test.pdf", page=1)
    assert c.content == "Hello"
    assert c.index == 0
    assert c.source == "test.pdf"
    assert c.page == 1
