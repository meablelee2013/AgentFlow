"""
Base parser interface — Strategy Pattern.

Each format parser implements this interface.
The RAGPipeline dispatches to the correct parser based on file extension.

```mermaid
classDiagram
    class BaseParser {
        <<abstract>>
        +supported_extensions: list[str]
        +parse(file_path) str
    }
    class PdfParser { +parse() str }
    class DocxParser { +parse() str }
    class MarkdownParser { +parse() str }
    class TxtParser { +parse() str }
    class CsvParser { +parse() str }
    class PptxParser { +parse() str }
    class JsonParser { +parse() str }
    class EpubParser { +parse() str }
    class HtmlParser { +parse() str }
    class UrlParser { +parse() str }

    BaseParser <|-- PdfParser
    BaseParser <|-- DocxParser
    BaseParser <|-- MarkdownParser
    BaseParser <|-- TxtParser
    BaseParser <|-- CsvParser
    BaseParser <|-- PptxParser
    BaseParser <|-- JsonParser
    BaseParser <|-- EpubParser
    BaseParser <|-- HtmlParser
    BaseParser <|-- UrlParser
```
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseParser(ABC):
    """Abstract base for all document parsers.

    Each subclass handles one file format and exposes a list of
    supported file extensions for auto-dispatch.
    """

    supported_extensions: list[str] = []

    @abstractmethod
    def parse(self, file_path: str) -> str:
        """Parse a file and return extracted text content."""
        ...

    def can_handle(self, file_path: str) -> bool:
        """Check if this parser can handle the given file."""
        ext = Path(file_path).suffix.lower()
        return ext in self.supported_extensions
