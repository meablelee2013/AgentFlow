"""Web search tool placeholder — Phase 2 MVP uses DuckDuckGo."""
from app.core.tool.base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for recent information. Returns top results."
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    }

    async def execute(self, query: str = "", **kwargs) -> ToolResult:
        """Placeholder: Phase 2 MVP returns a prompt to use external search.

        Phase 3: Integrate SerpAPI / Brave Search / Bing API.
        """
        if not query.strip():
            return ToolResult(success=False, output="", error="Query is empty")

        return ToolResult(
            success=True,
            output=(
                f"Web search for '{query}' is not configured yet. "
                "To enable: set SEARCH_API_KEY in .env. "
                "Supported: SerpAPI, Brave Search, Bing API."
            ),
            metadata={"query": query, "status": "not_configured"},
        )
