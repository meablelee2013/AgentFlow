"""URL parser — fetches and extracts text from web pages."""
from app.core.rag.parsers.base import BaseParser
from app.core.rag.parsers.html_parser import HtmlParser


class UrlParser(BaseParser):
    """Parse web pages by URL.

    Not file-extension based — used directly by the ingest_url pipeline.
    """

    supported_extensions = []  # Not extension-based

    def parse(self, file_path: str) -> str:
        raise NotImplementedError("Use UrlParser.fetch(url) for async HTTP requests")

    @staticmethod
    async def fetch(url: str) -> str:
        """Fetch a URL and extract clean text."""
        import httpx

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return HtmlParser._extract_text(resp.text)
