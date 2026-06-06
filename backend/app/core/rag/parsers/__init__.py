"""Document parsers — one class per file format, auto-dispatched via ParserRegistry."""
from app.core.rag.parsers.registry import ParserRegistry

__all__ = ["ParserRegistry"]
