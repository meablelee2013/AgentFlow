"""HTML parser — extracts text from local HTML files and URLs."""
from pathlib import Path
from bs4 import BeautifulSoup
from app.core.rag.parsers.base import BaseParser

NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]


class HtmlParser(BaseParser):
    """Parse local .html / .htm files."""

    supported_extensions = [".html", ".htm"]

    def parse(self, file_path: str) -> str:
        html = Path(file_path).read_text(encoding="utf-8")
        return self._extract_text(html)

    @staticmethod
    def _extract_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(NOISE_TAGS):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
