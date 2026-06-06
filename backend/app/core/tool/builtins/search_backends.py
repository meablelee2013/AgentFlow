"""
Search backends — pluggable web search providers.

Design: Strategy Pattern — each backend implements the same interface.
Add a new search provider by creating a class with a search() method.

Default: DuckDuckGo (free, unlimited, no API key)
Production: Tavily / Brave / SerpAPI (paid, higher quality)

```python
# Swap backends by changing one line:
backend = DuckDuckGoBackend()   # dev, free
backend = TavilyBackend()       # prod, $0.01/query
backend = BraveBackend()        # prod, 2000 free/month
```
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import os


@dataclass
class SearchResult:
    """Unified search result across all backends."""
    title: str
    url: str
    snippet: str

    def to_llm_text(self) -> str:
        return f"**{self.title}**\n{self.snippet}\n{self.url}"


# ── DuckDuckGo (free, unlimited) ──────────────────────────

class DuckDuckGoBackend:
    """Free web search via DuckDuckGo. No API key required.

    Rate limit: ~20 requests/minute (DDG's unofficial limit).
    Quality: Good for general queries, weaker for recent news.
    """

    name = "duckduckgo"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search DuckDuckGo and return structured results."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return [SearchResult(
                title="DuckDuckGo not installed",
                url="",
                snippet="Run: uv add duckduckgo-search"
            )]

        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                    ))
        except Exception:
            pass  # DDG rate limit or network error → return empty

        return results


# ── Tavily (paid, high quality) ────────────────────────────

class TavilyBackend:
    """Tavily Search API — optimized for AI agents.

    Free: 1000 queries/month
    Pro:  $0.01/query, higher rate limit
    Sign up: https://tavily.com
    """

    name = "tavily"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            from tavily import TavilyClient
        except ImportError:
            return [SearchResult(
                title="Tavily not installed",
                url="",
                snippet="Run: uv add tavily-python. Set TAVILY_API_KEY in .env"
            )]

        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return [SearchResult(
                title="Tavily API key not set",
                url="",
                snippet="Get a free key at https://tavily.com, then add TAVILY_API_KEY to .env"
            )]

        client = TavilyClient(api_key=api_key)
        response = client.search(query, max_results=max_results)
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            )
            for r in response.get("results", [])
        ]


# ── Brave Search (freemium) ────────────────────────────────

class BraveBackend:
    """Brave Search API — good free tier.

    Free: 2000 queries/month
    Paid: $5/1000 queries
    Sign up: https://brave.com/search/api/
    """

    name = "brave"

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        import httpx

        api_key = os.getenv("BRAVE_API_KEY", "")
        if not api_key:
            return [SearchResult(
                title="Brave API key not set",
                url="",
                snippet="Get a free key at https://brave.com/search/api/"
            )]

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
            data = resp.json()
            return [
                SearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("description", ""),
                )
                for r in data.get("web", {}).get("results", [])
            ]


# ── SearXNG (self-hosted, unlimited) ───────────────────────

class SearXNGBackend:
    """Self-hosted SearXNG metasearch — open source, no limits.

    Aggregates Google, Bing, Wikipedia, DDG, etc. (80+ engines).
    You control rate limits, privacy, and which engines to use.

    Deploy (one command):
        docker run -d -p 8080:8080 searxng/searxng

    Then set in .env:
        SEARXNG_URL=http://localhost:8080

    GitHub: https://github.com/searxng/searxng
    API docs: https://docs.searxng.org/dev/search_api.html

    Customization: edit deploy/searxng/settings.yml to:
      - Enable/disable specific engines (Google, Bing, Wikipedia...)
      - Set default language, safesearch, time range
      - Add API-key-only engines (e.g., Brave, Google via API)
    """

    name = "searxng"

    async def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        # Optional customization params (passed via kwargs from tool)
        language: str = "zh-CN",       # Search language: zh-CN, en, ja, fr...
        categories: str = "general",   # general, news, science, images, videos, it, files
        time_range: str = "",          # day, week, month, year (empty = any time)
        safesearch: int = 0,           # 0=off, 1=moderate, 2=strict
        engines: str = "",             # Comma-separated engine list, e.g. "google,bing,wikipedia"
    ) -> list[SearchResult]:
        import httpx

        base_url = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")

        # Build query params — SearXNG supports all these natively
        params: dict[str, str | int] = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": language,
            "safesearch": safesearch,
        }
        if time_range:
            params["time_range"] = time_range
        if engines:
            params["engines"] = engines

        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(f"{base_url}/search", params=params)
                resp.raise_for_status()
                data = resp.json()
                return [
                    SearchResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("content", ""),
                    )
                    for r in data.get("results", [])[:max_results]
                ]
            except Exception:
                return [SearchResult(
                    title="SearXNG not reachable",
                    url="",
                    snippet=f"Cannot connect to {base_url}. Deploy: docker run -d -p 8080:8080 searxng/searxng"
                )]


# ── Backend Factory ────────────────────────────────────────

def get_search_backend(name: str | None = None):
    """Get a search backend by name. Defaults to SearXNG, falls back to DDG.

    Set SEARCH_BACKEND in .env to override:
        SEARCH_BACKEND=searxng    → use SearXNG (default, self-hosted)
        SEARCH_BACKEND=tavily     → use Tavily
        SEARCH_BACKEND=brave      → use Brave
        SEARCH_BACKEND=duckduckgo → use DDG (free, unlimited)
    """
    backend_name = name or os.getenv("SEARCH_BACKEND", "searxng").lower()

    backends = {
        "searxng": SearXNGBackend,
        "duckduckgo": DuckDuckGoBackend,
        "tavily": TavilyBackend,
        "brave": BraveBackend,
    }

    backend_cls = backends.get(backend_name, SearXNGBackend)
    return backend_cls()
