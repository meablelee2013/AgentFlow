"""Plain text / Markdown parser."""
from pathlib import Path
from app.core.rag.parsers.base import BaseParser


class MarkdownParser(BaseParser):
    supported_extensions = [".md", ".markdown"]

    def parse(self, file_path: str) -> str:
        return Path(file_path).read_text(encoding="utf-8")


class TxtParser(BaseParser):
    supported_extensions = [".txt", ".text", ".log", ".csv"]

    def parse(self, file_path: str) -> str:
        return Path(file_path).read_text(encoding="utf-8")
