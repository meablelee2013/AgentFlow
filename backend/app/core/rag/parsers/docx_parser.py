"""DOCX parser — extracts text from Word documents."""
from app.core.rag.parsers.base import BaseParser


class DocxParser(BaseParser):
    supported_extensions = [".docx", ".doc"]

    def parse(self, file_path: str) -> str:
        from docx import Document as DocxDocument

        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
