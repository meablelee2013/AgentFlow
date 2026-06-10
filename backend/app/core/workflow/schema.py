"""
Workflow DSL Schema — JSON-based workflow definition for the visual editor.

A workflow is a directed graph of nodes and edges, compiled to LangGraph.

Node data flow (Coze-style):
    - Each node has explicit `inputs` and `outputs` declarations
    - Inputs reference upstream outputs via `{{node_x.field}}` templates
    - The start node defines global input parameters ({{input.xxx}})
    - System variables like {{sys.user_id}} are also available
"""

from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
import uuid


class NodePosition(BaseModel):
    x: float = 0
    y: float = 0


class NodeIOParam(BaseModel):
    """A single input or output parameter for a workflow node.

    For inputs:
      - source="reference": ref points to an upstream output like "node_1.body.items"
      - source="literal": value is a fixed constant like 100 or "hello"

    For outputs:
      - Only name, type, and description are used (source/ref/value are ignored)
    """
    name: str
    type: Literal["string", "number", "boolean", "object", "array", "any"] = "any"
    description: str = ""

    # Input-only fields
    source: Literal["reference", "literal"] = "reference"
    ref: str = ""          # e.g. "node_1.body.items" or "input.query"
    value: Any = None      # fixed literal value when source="literal"
    required: bool = False


# ── Node-specific config models ──────────────────────────────

class ChatNodeData(BaseModel):
    system_prompt: str = ""


class RAGNodeData(BaseModel):
    knowledge_base_id: str = ""


class ToolNodeData(BaseModel):
    tool_name: str = ""


class ConditionNodeData(BaseModel):
    field: str = ""
    operator: Literal["equals", "contains", "gt", "lt"] = "contains"
    value: str = ""
    true_branch: str = ""   # target node id
    false_branch: str = ""  # target node id


class LoopNodeData(BaseModel):
    input_field: str = ""
    max_iterations: int = 5


class HITLNodeData(BaseModel):
    approval_message: str = "Approve this action?"


class HTTPAPINodeData(BaseModel):
    """HTTP API node — call external APIs with authentication."""
    url: str = ""
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    headers: dict[str, str] = {}
    query_params: dict[str, str] = {}
    body: str = ""
    timeout: int = 30
    retry_count: int = 0

    # Auth
    auth_mode: Literal["none", "bearer", "api_key", "basic", "login_flow"] = "none"
    credential_id: str = ""

    # api_key mode
    api_key_location: Literal["header", "query"] = "header"
    api_key_name: str = "X-API-Key"

    # login_flow mode (enterprise internal systems)
    login_url: str = ""
    login_method: str = "POST"
    login_body: str = ""
    token_path: str = "$.data.token"
    token_header_name: str = "Authorization"
    token_header_format: str = "Bearer {token}"
    token_ttl: int = 3600

    # Response
    response_path: str = ""     # JSONPath to extract from response body


class DatabaseNodeData(BaseModel):
    """Database node — query PostgreSQL / MySQL."""
    credential_id: str = ""
    db_type: Literal["postgresql", "mysql"] = "postgresql"
    sql: str = ""
    read_only: bool = True
    max_rows: int = 1000
    timeout: int = 30


class CodeNodeData(BaseModel):
    """Code node — execute Python in Docker sandbox.

    Entry point must be: async def main(args):
    args is a dict with declared input parameters.
    Must return a dict.
    """
    code: str = ""
    language: Literal["python"] = "python"
    timeout: int = 30
    memory_limit: str = "256m"


# ── Task Decomposition node configs ──────────────────────────

class DecomposeNodeData(BaseModel):
    """Decompose node — LLM breaks a complex goal into independent subtasks."""
    enabled_capabilities: list[str] = []  # e.g. ["web_search", "agent:analyst"]
    system_prompt: str = ""               # custom decomposition prompt (empty = use default)
    max_subtasks: int = 10


class AggregateNodeData(BaseModel):
    """Aggregate node — collect subtask results and synthesize a final report."""
    summary_prompt: str = ""              # custom aggregation prompt
    failure_mode: Literal["partial", "strict"] = "partial"


# ── Task Decomposition runtime models ─────────────────────────

class SubTask(BaseModel):
    """A single subtask produced by the Decompose node."""
    id: str
    description: str = ""
    executor: str = ""                    # capability_id: "web_search" | "agent:analyst"
    depends_on: list[str] = []            # subtask IDs that must complete before this one
    input: dict[str, Any] = {}
    expected_output: str = ""
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    result: Any = None
    error: str | None = None
    duration_ms: int = 0


class ExecutionTrace(BaseModel):
    """Complete execution trace for a task decomposition run."""
    execution_id: str = ""
    total: int = 0
    completed: int = 0
    failed: int = 0
    total_duration_ms: int = 0
    subtasks: list[SubTask] = []
    aggregated_output: str = ""


# ── Core workflow schema ──────────────────────────────────────

class WorkflowNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal[
        "start", "chat", "rag", "search", "tool",
        "condition", "loop", "hitl", "end",
        "http_api", "database", "code",
        "decompose", "aggregate",    # ← Task decomposition nodes
    ]
    position: NodePosition = Field(default_factory=NodePosition)
    inputs: list[NodeIOParam] = []     # Declared input parameters (Coze-style)
    outputs: list[NodeIOParam] = []    # Declared output schema
    data: dict = Field(default_factory=dict)


class WorkflowEdge(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str
    target: str
    source_handle: str | None = None
    label: str | None = None


class WorkflowDefinition(BaseModel):
    """Complete workflow DSL definition."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Workflow"
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)

    def get_node(self, node_id: str) -> WorkflowNode | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_outgoing(self, node_id: str) -> list[WorkflowEdge]:
        return [e for e in self.edges if e.source == node_id]

    def get_start_node(self) -> WorkflowNode | None:
        for n in self.nodes:
            if n.type == "start":
                return n
        return None
