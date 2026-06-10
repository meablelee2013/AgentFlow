"""
Capability Registry — global registry of all available executors.

The registry auto-discovers builtin node types and agent types at startup.
Decompose nodes query the registry to present available capabilities to the LLM.

Two categories:
  - builtin_node: Single-call executors (web_search, http_api, database, code, etc.)
  - agent: Multi-step ReAct executors (analyst, coder, writer, custom agents)
"""

from __future__ import annotations
from typing import Any
from dataclasses import dataclass, field


@dataclass
class ExecutorCapability:
    """A single capability that can execute a subtask."""
    id: str                      # "web_search" | "http_api" | "agent:analyst"
    type: str                    # "builtin_node" | "agent"
    label: str                   # "Web Search"
    description: str             # "Search the internet for information"
    input_schema: dict[str, Any] = field(default_factory=dict)
    # Agent-only fields
    system_prompt: str | None = None
    tools: list[str] | None = None
    max_iterations: int = 10

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "description": self.description,
            "input_schema": self.input_schema,
        }
        if self.type == "agent":
            result["tools"] = self.tools or []
            result["max_iterations"] = self.max_iterations
        return result

    def to_llm_description(self) -> str:
        """Format for inclusion in Decompose LLM prompt."""
        input_desc = ", ".join(
            f"{k} ({v.get('type', 'any')})" + ("*" if v.get("required") else "")
            for k, v in self.input_schema.items()
        ) if self.input_schema else "no input required"
        return (
            f"- `{self.id}` ({self.type}): {self.description}\n"
            f"  Input: {input_desc}"
        )


# ── Builtin Node Capabilities ──────────────────────────────────────

BUILTIN_CAPABILITIES: dict[str, ExecutorCapability] = {
    "web_search": ExecutorCapability(
        id="web_search",
        type="builtin_node",
        label="Web Search",
        description="Search the internet for information. Best for research, fact-checking, finding current news or data.",
        input_schema={"query": {"type": "string", "required": True, "description": "Search query string"}},
    ),
    "http_api": ExecutorCapability(
        id="http_api",
        type="builtin_node",
        label="HTTP API",
        description="Call external HTTP APIs to fetch or send data. Best for accessing structured data from services.",
        input_schema={
            "url": {"type": "string", "required": True, "description": "API endpoint URL"},
            "method": {"type": "string", "required": False, "description": "HTTP method (GET/POST/PUT/DELETE)"},
            "headers": {"type": "object", "required": False, "description": "Request headers"},
            "body": {"type": "string", "required": False, "description": "Request body (JSON string)"},
        },
    ),
    "chat": ExecutorCapability(
        id="chat",
        type="builtin_node",
        label="Chat / LLM",
        description="Use a large language model for reasoning, summarization, translation, or text generation. Best for analysis, writing, or answering questions with existing knowledge.",
        input_schema={"prompt": {"type": "string", "required": True, "description": "Instruction or question for the LLM"}},
    ),
    "rag": ExecutorCapability(
        id="rag",
        type="builtin_node",
        label="Knowledge Base (RAG)",
        description="Search the connected knowledge base for relevant documents. Best for answering questions about company policies, manuals, or documentation.",
        input_schema={"query": {"type": "string", "required": True, "description": "Search query for the knowledge base"}},
    ),
    "database": ExecutorCapability(
        id="database",
        type="builtin_node",
        label="Database Query",
        description="Execute SQL queries against connected databases. Best for fetching structured data, reports, or analytics.",
        input_schema={"sql": {"type": "string", "required": True, "description": "SQL query to execute"}},
    ),
    "code": ExecutorCapability(
        id="code",
        type="builtin_node",
        label="Code Execution",
        description="Execute Python code in a sandbox. Best for data processing, calculations, format conversion, or custom logic.",
        input_schema={"code": {"type": "string", "required": True, "description": "Python code to execute"}},
    ),
}


# ── Agent Capabilities ─────────────────────────────────────────────

DEFAULT_AGENT_CAPABILITIES: dict[str, ExecutorCapability] = {
    "agent:analyst": ExecutorCapability(
        id="agent:analyst",
        type="agent",
        label="Analyst Agent",
        description="A multi-step reasoning agent specialized in data analysis, comparison, and generating structured reports. Can use tools for calculations and data retrieval.",
        input_schema={"task": {"type": "string", "required": True, "description": "Analysis task description with context"}},
        tools=["calculator", "web_search"],
        max_iterations=10,
    ),
    "agent:coder": ExecutorCapability(
        id="agent:coder",
        type="agent",
        label="Coder Agent",
        description="A code-focused agent that can write, debug, and execute scripts. Best for data processing, automation, or complex computational tasks.",
        input_schema={"task": {"type": "string", "required": True, "description": "Coding task description"}},
        tools=["code_executor", "file_search"],
        max_iterations=10,
    ),
    "agent:writer": ExecutorCapability(
        id="agent:writer",
        type="agent",
        label="Writer Agent",
        description="A writing agent that can research, draft, and refine long-form content. Best for reports, articles, or documentation.",
        input_schema={"task": {"type": "string", "required": True, "description": "Writing task with requirements and style guidance"}},
        tools=["web_search"],
        max_iterations=8,
    ),
}


class CapabilityRegistry:
    """Global registry of all available executor capabilities.

    Usage:
        registry = CapabilityRegistry()
        cap = registry.get("web_search")
        all_caps = registry.list_all()
        prompt_caps = registry.describe_for_prompt(["web_search", "agent:analyst"])
    """

    def __init__(self):
        self._builtin_nodes: dict[str, ExecutorCapability] = dict(BUILTIN_CAPABILITIES)
        self._agents: dict[str, ExecutorCapability] = dict(DEFAULT_AGENT_CAPABILITIES)

    def get(self, capability_id: str) -> ExecutorCapability | None:
        """Get a single capability by ID."""
        return self._builtin_nodes.get(capability_id) or self._agents.get(capability_id)

    def list_builtin(self) -> list[ExecutorCapability]:
        """List all builtin node capabilities."""
        return list(self._builtin_nodes.values())

    def list_agents(self) -> list[ExecutorCapability]:
        """List all agent capabilities."""
        return list(self._agents.values())

    def list_all(self) -> list[ExecutorCapability]:
        """List all capabilities (builtin + agents)."""
        return self.list_builtin() + self.list_agents()

    def list_enabled(self, enabled_ids: list[str]) -> list[ExecutorCapability]:
        """Get only the capabilities whose IDs are in enabled_ids."""
        result = []
        for cid in enabled_ids:
            cap = self.get(cid)
            if cap:
                result.append(cap)
        return result

    def describe_for_prompt(self, enabled_ids: list[str]) -> str:
        """Format enabled capabilities for inclusion in the Decompose LLM prompt."""
        caps = self.list_enabled(enabled_ids) if enabled_ids else self.list_all()
        lines = ["## Available Capabilities\n"]
        for cap in caps:
            lines.append(cap.to_llm_description())
        return "\n".join(lines)

    def register_builtin(self, capability: ExecutorCapability):
        """Register a new builtin node capability."""
        self._builtin_nodes[capability.id] = capability

    def register_agent(self, capability: ExecutorCapability):
        """Register a new agent capability."""
        self._agents[capability.id] = capability

    def to_api_response(self) -> dict:
        """Format for the GET /api/v1/capabilities API response."""
        return {
            "builtin_nodes": [cap.to_dict() for cap in self.list_builtin()],
            "agents": [cap.to_dict() for cap in self.list_agents()],
        }


# ── Singleton ──────────────────────────────────────────────────────

_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    """Get the global capability registry singleton."""
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
