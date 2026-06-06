"""PDF parser — extracts text from PDF files."""
from app.core.rag.parsers.base import BaseParser


class PdfParser(BaseParser):
    supported_extensions = [".pdf"]

    def parse(self, file_path: str) -> str:
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
