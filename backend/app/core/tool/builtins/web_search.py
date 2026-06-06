"""Web search tool — LangChain BaseTool, multi-backend (SearXNG/DDG/Tavily/Brave)."""
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.core.tool.builtins.search_backends import get_search_backend


class WebSearchInput(BaseModel):
    """Input schema for web search — auto-generated as JSON Schema for LLM."""
    query: str = Field(description="The search query")
    time_range: str = Field(
        default="",
        description="Time filter: empty=any, day, week, month, year",
    )
    language: str = Field(
        default="zh-CN",
        description="Language code: zh-CN, en, ja, fr...",
    )


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web for recent or factual information. "
        "Use this when you need to find current news, verify facts, "
        "or look up information beyond your training data."
    )
    args_schema: type[BaseModel] = WebSearchInput

    async def _arun(self, query: str = "", time_range: str = "", language: str = "zh-CN") -> str:
        if not query.strip():
            return "Error: query is empty"

        backend = get_search_backend()
        results = await backend.search(
            query, max_results=5,
            time_range=time_range, language=language,
        )

        if not results:
            return f"No results found for '{query}'. Try rewording."

        lines = [f"Search results for '{query}' (via {backend.name}):\n"]
        for i, r in enumerate(results):
            lines.append(f"{i + 1}. {r.to_llm_text()}")
        return "\n\n".join(lines)

    def _run(self, query: str = "", time_range: str = "", language: str = "zh-CN") -> str:
        raise NotImplementedError("Use _arun (async)")
