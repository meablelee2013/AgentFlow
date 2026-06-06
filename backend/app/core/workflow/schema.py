"""
Workflow DSL Schema — JSON-based workflow definition for the visual editor.

A workflow is a directed graph of nodes and edges, compiled to LangGraph.
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field
import uuid


class NodePosition(BaseModel):
    x: float = 0
    y: float = 0


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


class WorkflowNode(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: Literal["start", "chat", "rag", "search", "tool", "condition", "loop", "hitl", "end"]
    position: NodePosition = Field(default_factory=NodePosition)
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
