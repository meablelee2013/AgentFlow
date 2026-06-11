"""MCP HTTP client manager — connection lifecycle and tool discovery.

Design pattern: **Module-level singleton with explicit lifecycle**
    The FastAPI lifespan manages the async context managers
    (streamable_http_client + ClientSession). Once initialized,
    the session reference is stored on this singleton for use
    by the chat engine at request time.

Usage:
    # In FastAPI lifespan:
    manager = get_mcp_client()
    async with streamable_http_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            manager._set_session(session)
            await manager.discover_tools()
            yield  # app runs
            manager._clear_session()
"""

import structlog
from mcp.client.session import ClientSession
from mcp.types import Tool as MCPTool, CallToolResult

logger = structlog.get_logger()


class MCPClientManager:
    """Manages MCP connection state.

    Lifecycle:
      1. lifespan calls _set_session(session) + discover_tools()
      2. Request handlers call call_tool(name, arguments)
      3. lifespan calls _clear_session()
    """

    def __init__(self):
        self._session: ClientSession | None = None
        self._tools: dict[str, MCPTool] = {}
        self._initialized: bool = False

    def _set_session(self, session: ClientSession) -> None:
        """Store the initialized session. Called from lifespan."""
        self._session = session
        self._initialized = True

    def _clear_session(self) -> None:
        """Clear the session. Called from lifespan after yield."""
        self._session = None
        self._tools = {}
        self._initialized = False

    async def discover_tools(self) -> list[MCPTool]:
        """List tools from the connected MCP server and cache them.

        Returns:
            List of MCP Tool objects discovered.

        Raises:
            RuntimeError: if no session is active.
        """
        if self._session is None:
            raise RuntimeError("MCP session not initialized. Call _set_session first.")

        result = await self._session.list_tools()
        self._tools = {t.name: t for t in result.tools}
        logger.info(
            "mcp_tools_discovered",
            count=len(self._tools),
            tools=list(self._tools.keys()),
        )
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict) -> str:
        """Call an MCP tool and return its text output.

        Args:
            name: Tool name (e.g. "cmapi00074002____15___").
            arguments: Tool arguments as a dict (e.g. {"cityname": "Beijing"}).

        Returns:
            Tool result formatted as a text string.

        Raises:
            RuntimeError: if no session is active.
        """
        if self._session is None:
            raise RuntimeError(
                "MCP session not initialized. Cannot call tool."
            )

        logger.debug("mcp_call_tool", name=name, args=arguments)
        result: CallToolResult = await self._session.call_tool(name, arguments)

        if result.isError:
            error_text = _extract_text(result)
            logger.warning("mcp_tool_error", name=name, error=error_text)
            return f"Error from tool '{name}': {error_text}"

        return _extract_text(result)

    @property
    def tools(self) -> dict[str, MCPTool]:
        """All discovered tools, keyed by name."""
        return self._tools

    @property
    def is_initialized(self) -> bool:
        """Whether the MCP session is active and tools are available."""
        return self._initialized and self._session is not None

    def build_tools_description(self) -> str:
        """Build a Markdown description of available MCP tools.

        Used to populate PromptContext.tools_description for the
        layered prompt builder's ToolsLayer.
        """
        if not self._tools:
            return ""

        lines = ["## Available Weather Tools", ""]
        for name, tool in self._tools.items():
            desc = tool.description or "No description"
            lines.append(f"- **{name}**: {desc}")

        lines.append("")
        lines.append(
            "When asked about weather, always use these tools to get "
            "real data instead of making up information."
        )
        return "\n".join(lines)


def _extract_text(result: CallToolResult) -> str:
    """Extract text content from a CallToolResult."""
    parts: list[str] = []
    for block in result.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    if not parts and result.structuredContent:
        return str(result.structuredContent)
    return "\n".join(parts) if parts else "(empty result)"


# ── Module-level singleton ──────────────────────────────────────

_mcp_manager: MCPClientManager | None = None


def get_mcp_client() -> MCPClientManager:
    """Get or create the module-level MCP client singleton.

    Returns:
        The shared MCPClientManager instance.
    """
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
    return _mcp_manager
