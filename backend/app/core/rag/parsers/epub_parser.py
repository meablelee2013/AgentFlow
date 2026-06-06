"""EPUB parser — extracts text from e-book files."""
from app.core.rag.parsers.base import BaseParser


class EpubParser(BaseParser):
    supported_extensions = [".epub"]

    def parse(self, file_path: str) -> str:
        from ebooklib import epub
        from bs4 import BeautifulSoup

        book = epub.read_epub(file_path)
        chapters = []
        for item in book.get_items_of_type(9):  # ITEM_DOCUMENT = 9
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if text:
                chapters.append(text)
        return "\n\n".join(chapters)
