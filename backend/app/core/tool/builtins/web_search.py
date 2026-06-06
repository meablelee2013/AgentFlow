"""Web search tool — multi-backend with auto-fallback."""
from app.core.tool.base import BaseTool, ToolResult
from app.core.tool.builtins.search_backends import get_search_backend


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for recent or factual information. "
        "Use this when you need to find current news, verify facts, "
        "or look up information beyond your training data."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "time_range": {
                "type": "string",
                "enum": ["", "day", "week", "month", "year"],
                "description": "Time filter: empty=any time, day, week, month, year",
            },
            "language": {
                "type": "string",
                "description": "Search language code, e.g. zh-CN, en, ja",
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str = "", time_range: str = "", language: str = "zh-CN", **kwargs) -> ToolResult:
        if not query.strip():
            return ToolResult(success=False, output="", error="Query is empty")

        backend = get_search_backend()
        results = await backend.search(
            query, max_results=5,
            time_range=time_range, language=language,
        )

        if not results:
            return ToolResult(
                success=True,
                output=f"No results found for '{query}'. Try rewording or use a broader query.",
            )

        # Format results as Markdown for LLM consumption
        lines = [f"Search results for '{query}' (via {backend.name}):\n"]
        for i, r in enumerate(results):
            lines.append(f"{i + 1}. {r.to_llm_text()}")

        return ToolResult(
            success=True,
            output="\n\n".join(lines),
            metadata={"backend": backend.name, "count": len(results)},
        )
