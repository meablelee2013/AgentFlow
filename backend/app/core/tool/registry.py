"""
ToolRegistry — manages tool registration and discovery.

Design pattern: **Registry Pattern**
    Tools register themselves at init time. The registry provides
    tool lookup by name and schema generation for LLM function calling.
"""

from app.core.tool.base import BaseTool, ToolResult


class ToolRegistry:
    """Central registry for all available tools.

    Usage:
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        schemas = registry.get_openai_schemas()
        result = await registry.execute("calculator", expression="2+2")
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance."""
        if not tool.name:
            raise ValueError(f"Tool {tool} has no name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_openai_schemas(self) -> list[dict]:
        """Get OpenAI-compatible function schemas for all tools."""
        return [t.to_openai_schema() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with given arguments."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool '{name}' not found. Available: {self.list_tools()}",
            )
        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
