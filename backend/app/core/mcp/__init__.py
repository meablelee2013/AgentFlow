"""MCP integration — connect to external MCP servers and expose tools to the chat engine.

Package structure:
    config              — read .mcp.json, parse server definitions
    client              — MCPClientManager: HTTP connection lifecycle + tool discovery
    langchain_adapter   — convert MCP Tools to LangChain BaseTool instances
"""

from app.core.mcp.config import MCPConfig, MCPServerConfig
from app.core.mcp.client import MCPClientManager, get_mcp_client
from app.core.mcp.langchain_adapter import build_mcp_langchain_tools

__all__ = [
    "MCPConfig",
    "MCPServerConfig",
    "MCPClientManager",
    "get_mcp_client",
    "build_mcp_langchain_tools",
]
