"""MCP configuration reader — parses .mcp.json at the project root.

Design pattern: **Configuration Object**
    Read once at startup, cache as a module-level singleton.
    Only HTTP-type servers are supported (streamable HTTP transport).
"""

from dataclasses import dataclass, field
from pathlib import Path
import json
import structlog

logger = structlog.get_logger()


@dataclass
class MCPServerConfig:
    """A single MCP server definition from .mcp.json."""

    name: str
    type: str  # "http"
    url: str


@dataclass
class MCPConfig:
    """Aggregated MCP configuration — all servers from .mcp.json."""

    servers: list[MCPServerConfig] = field(default_factory=list)

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> "MCPConfig":
        """Read .mcp.json from the project root and return a typed config.

        Args:
            project_root: Path to the project root. If None, auto-detected
                from this file's location (goes up 4 levels from
                app/core/mcp/config.py → project root).

        Returns:
            MCPConfig with parsed servers. Returns empty config if
            .mcp.json is missing or unreadable.
        """
        if project_root is None:
            # config.py lives at: backend/app/core/mcp/config.py
            # Project root is 4 levels up
            project_root = Path(__file__).resolve().parents[4]

        mcp_json = project_root / ".mcp.json"
        if not mcp_json.exists():
            logger.debug("no_mcp_json", path=str(mcp_json))
            return cls()

        try:
            raw = json.loads(mcp_json.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("mcp_json_parse_error", path=str(mcp_json), error=str(e))
            return cls()

        servers: list[MCPServerConfig] = []
        for name, svr in raw.get("mcpServers", {}).items():
            svr_type = svr.get("type", "")
            if svr_type not in ("http", "streamableHttp"):
                logger.debug(
                    "mcp_skip_unsupported_transport",
                    server=name,
                    type=svr_type,
                )
                continue
            servers.append(
                MCPServerConfig(
                    name=name,
                    type=svr_type,
                    url=svr["url"],
                )
            )

        logger.info("mcp_config_loaded", server_count=len(servers))
        return cls(servers=servers)
