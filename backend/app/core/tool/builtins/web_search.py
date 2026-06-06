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
                "description": "The search query, e.g. 'latest AI news 2026'",
            }
        },
        "required": ["query"],
    }

    async def execute(self, query: str = "", **kwargs) -> ToolResult:
        if not query.strip():
            return ToolResult(success=False, output="", error="Query is empty")

        backend = get_search_backend()
        results = await backend.search(query, max_results=5)

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
