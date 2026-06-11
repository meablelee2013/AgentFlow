"""MCP Tool → LangChain BaseTool adapter.

Converts MCP Tool definitions (discovered at runtime from the MCP server)
into LangChain BaseTool instances that can be used with ChatOpenAI.bind_tools().

The key conversion is:
    MCP Tool.inputSchema (JSON Schema dict)
        → Pydantic BaseModel (args_schema)
        → LangChain BaseTool (bind_tools compatible)

Design pattern: **Adapter Pattern**
    Wraps an MCP tool behind the LangChain BaseTool interface so the chat
    engine doesn't need to know about MCP internals.
"""

from typing import Any
from pydantic import BaseModel, Field, create_model
from langchain_core.tools import BaseTool as LCTool
from mcp.types import Tool as MCPTool


# ── JSON Schema → Python type mapping ────────────────────────────

_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_type_to_python(prop_schema: dict) -> type:
    """Map a JSON Schema property to a Python type.

    Handles:
    - Direct type mapping (string→str, integer→int, etc.)
    - type array (e.g. ["string", "null"]) — picks the first non-null type
    - Missing type — defaults to str
    """
    raw_type = prop_schema.get("type", "string")

    # Handle union types like ["string", "null"]
    if isinstance(raw_type, list):
        for t in raw_type:
            if t != "null":
                return _JSON_TYPE_MAP.get(t, str)
        return str

    return _JSON_TYPE_MAP.get(raw_type, str)


def _json_schema_to_pydantic_model(
    tool_name: str, input_schema: dict
) -> type[BaseModel]:
    """Convert a JSON Schema object to a Pydantic BaseModel subclass.

    Used as the args_schema for the LangChain BaseTool.

    Args:
        tool_name: The MCP tool name (used to derive a unique class name).
        input_schema: The MCP tool's inputSchema dict with "properties"
            and optionally "required" keys.

    Returns:
        A dynamically created Pydantic BaseModel subclass.
    """
    required_fields: set[str] = set(input_schema.get("required", []))
    properties = input_schema.get("properties", {})

    fields: dict[str, tuple[type, Any]] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _json_type_to_python(prop_schema)
        description = prop_schema.get("description", "")

        if prop_name in required_fields:
            fields[prop_name] = (py_type, Field(description=description))
        else:
            fields[prop_name] = (
                py_type | None,
                Field(default=None, description=description),
            )

    # If no properties defined, create a model with no fields
    if not fields:
        fields["_placeholder"] = (str | None, Field(default=None))

    # Sanitize tool name for a valid Python class name
    safe_name = "".join(
        c if c.isalnum() or c == "_" else "_" for c in tool_name
    ).strip("_")
    class_name = f"MCPTool_{safe_name}_Input"

    return create_model(class_name, **fields)  # type: ignore[call-overload]


# ── Tool name sanitization ────────────────────────────────────────
# DeepSeek API requires tool names matching ^[a-zA-Z0-9_-]+$
# Chinese MCP tool names must be converted to ASCII-safe equivalents.

def _sanitize_tool_name(mcp_name: str, input_schema: dict) -> str:
    """Convert a Chinese MCP tool name to an ASCII-safe LangChain tool name.

    Uses keyword matching from the Chinese name and input parameters
    to create a readable ASCII identifier.

    Examples:
        城市天气实况 (cityname)     → weather_current_by_city
        经纬度15日预报 (lat, lon)   → weather_15day_forecast_by_latlon
        城市ID生活指数 (cityId)     → living_index_by_cityid
    """
    # Determine the parameter key (how the tool is queried)
    properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
    param_keys = list(properties.keys())

    if "poi" in param_keys:
        param_suffix = "by_poi"
    elif "cityname" in param_keys:
        param_suffix = "by_city"
    elif "cityId" in param_keys:
        param_suffix = "by_cityid"
    elif "lat" in param_keys and "lon" in param_keys:
        param_suffix = "by_latlon"
    elif "lat" in param_keys:
        param_suffix = "by_lat"
    elif "lon" in param_keys:
        param_suffix = "by_lon"
    else:
        param_suffix = ""

    # Match Chinese keywords to English function types
    name = mcp_name

    # Order matters: check longer/more specific patterns first
    if "临近降水" in name:
        func = "precipitation"
    elif "24小时" in name and "空气" in name:
        func = "air_quality_24h"
    elif "24小时" in name:
        func = "weather_24h"
    elif "15日" in name and "空气" in name:
        func = "air_quality_15d"
    elif "15日" in name:
        func = "weather_15d"
    elif "40日" in name:
        func = "weather_40d"
    elif "100日" in name:
        func = "weather_100d"
    elif "天气实况" in name:
        func = "weather_current"
    elif "空气实况" in name:
        func = "air_quality_current"
    elif "生活指数" in name:
        func = "living_index"
    elif "天气预警" in name:
        func = "weather_alert"
    elif "限行" in name:
        func = "traffic_restriction"
    elif "空气" in name:
        func = "air_quality"
    elif "天气" in name:
        func = "weather"
    else:
        # Fallback: use a short hash of the original name
        func = f"weather_tool_{hash(mcp_name) & 0xFFFF:04x}"

    parts = [func]
    if param_suffix:
        parts.append(param_suffix)
    return "_".join(parts)


# ── MCP Tool wrapper class ────────────────────────────────────────

class _MCPToolWrapper(LCTool):
    """Wraps a single MCP tool as a LangChain BaseTool.

    Uses Pydantic field declarations compatible with BaseTool's
    model inheritance. Each instance wraps one MCP tool.
    """

    name: str = ""
    description: str = ""
    args_schema: type[BaseModel] = BaseModel
    _call_fn: Any = None
    _tool_name: str = ""

    async def _arun(self, **kwargs: Any) -> str:
        """Execute the MCP tool via the injected call_fn."""
        if self._call_fn is None:
            return "Error: tool not properly initialized"
        return await self._call_fn(self._tool_name, **kwargs)

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError("Use _arun (async)")


# ── MCP → LangChain adapter ──────────────────────────────────────

def mcp_tool_to_langchain(
    mcp_tool: MCPTool,
    call_fn: Any,
) -> LCTool:
    """Convert a single MCP Tool to a LangChain BaseTool.

    Args:
        mcp_tool: The MCP Tool definition (name, description, inputSchema).
        call_fn: Async callable with signature:
            async def call_fn(tool_name: str, **kwargs) -> str
            The closure captures the MCP client and delegates to it.

    Returns:
        A LangChain BaseTool subclass instance ready for bind_tools().
    """
    mcp_name = mcp_tool.name  # Original MCP tool name (Chinese, for calling)
    input_schema = mcp_tool.inputSchema if isinstance(mcp_tool.inputSchema, dict) else {}

    # Create ASCII-safe LangChain tool name
    lc_name = _sanitize_tool_name(mcp_name, input_schema)

    # Description: include original Chinese name so LLM knows what this is
    original_desc = mcp_tool.description or f"MCP tool: {mcp_name}"
    description = f"[{mcp_name}] {original_desc}"

    # Build Pydantic args_schema from MCP inputSchema
    if isinstance(mcp_tool.inputSchema, dict) and mcp_tool.inputSchema.get("type") == "object":
        args_schema = _json_schema_to_pydantic_model(lc_name, input_schema)
    else:
        class _NoArgs(BaseModel):
            pass
        args_schema = _NoArgs

    # Create a wrapper instance
    wrapper = _MCPToolWrapper()
    wrapper.name = lc_name
    wrapper.description = description
    wrapper.args_schema = args_schema
    wrapper._call_fn = call_fn
    wrapper._tool_name = mcp_name  # Store original name for MCP calls

    return wrapper


# ── Batch builder ────────────────────────────────────────────────

async def build_mcp_langchain_tools(
    manager: Any,  # MCPClientManager (avoid circular import)
) -> list[LCTool]:
    """Build LangChain BaseTool instances from all discovered MCP tools.

    Args:
        manager: An MCPClientManager with an active session and
            discovered tools.

    Returns:
        List of LangChain BaseTool instances, one per MCP tool.
    """
    tools: list[LCTool] = []

    for name, mcp_tool in manager.tools.items():

        async def _call_mcp_tool(tool_name: str = name, **kwargs: Any) -> str:
            """Closure that captures tool_name and delegates to the MCP manager."""
            return await manager.call_tool(tool_name, kwargs)

        lc_tool = mcp_tool_to_langchain(mcp_tool, _call_mcp_tool)
        tools.append(lc_tool)

    return tools
