"""
ParserRegistry — auto-dispatches file parsing to the correct parser.

Design pattern: **Registry + Strategy**
    Each parser registers itself with supported file extensions.
    The registry auto-selects based on extension, keeping the caller
    decoupled from specific format implementations.

Usage:
    registry = ParserRegistry()
    text = registry.parse("/path/to/doc.pdf")  # Auto-uses PdfParser
"""

from pathlib import Path
from app.core.rag.parsers.base import BaseParser

from app.core.rag.parsers.pdf_parser import PdfParser
from app.core.rag.parsers.docx_parser import DocxParser
from app.core.rag.parsers.text_parser import MarkdownParser, TxtParser
from app.core.rag.parsers.csv_parser import CsvParser, ExcelParser
from app.core.rag.parsers.pptx_parser import PptxParser
from app.core.rag.parsers.json_parser import JsonParser
from app.core.rag.parsers.epub_parser import EpubParser
from app.core.rag.parsers.html_parser import HtmlParser


class ParserRegistry:
    """Auto-dispatching parser registry.

    All parser instances are registered at init time.
    Call parse() with any supported file path and it
    automatically routes to the correct parser.
    """

    def __init__(self):
        self._parsers: list[BaseParser] = [
            PdfParser(),
            DocxParser(),
            MarkdownParser(),
            TxtParser(),
            CsvParser(),
            ExcelParser(),
            PptxParser(),
            JsonParser(),
            EpubParser(),
            HtmlParser(),
        ]
        # Build extension → parser lookup
        self._by_ext: dict[str, BaseParser] = {}
        for parser in self._parsers:
            for ext in parser.supported_extensions:
                self._by_ext[ext] = parser

    def parse(self, file_path: str) -> str:
        """Parse a file, auto-detecting format from extension.

        Args:
            file_path: Path to the file

        Returns:
            Extracted text content

        Raises:
            ValueError: If the file extension is not supported
        """
        ext = Path(file_path).suffix.lower()
        parser = self._by_ext.get(ext)
        if parser is None:
            supported = ", ".join(sorted(self._by_ext.keys()))
            raise ValueError(
                f"Unsupported file type '{ext}'. Supported: {supported}"
            )
        return parser.parse(file_path)

    @property
    def supported_extensions(self) -> list[str]:
        """Return all supported file extensions."""
        return sorted(self._by_ext.keys())
