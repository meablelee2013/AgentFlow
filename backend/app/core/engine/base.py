"""
Graph Engine abstract base class

LangGraph execution lifecycle:
```mermaid
sequenceDiagram
    participant User
    participant FastAPI
    participant GraphEngine
    participant StateGraph
    participant Checkpointer

    User->>FastAPI: POST /chat {message, thread_id}
    FastAPI->>GraphEngine: run(messages, config)
    GraphEngine->>Checkpointer: get_tuple(config)
    Checkpointer-->>GraphEngine: previous state (or None)
    GraphEngine->>StateGraph: compile(checkpointer)
    StateGraph->>StateGraph: ainvoke(state, config)
    Note over StateGraph: each superstep:
    StateGraph->>Checkpointer: put_writes(writes)
    StateGraph->>Checkpointer: put(checkpoint, metadata)
    StateGraph-->>GraphEngine: final state
    GraphEngine-->>FastAPI: response + thread_id
    FastAPI-->>User: SSE stream / JSON response
```
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator


class BaseGraphEngine(ABC):
    """LangGraph engine abstract base class

    Defines the contract for all Graph Engines.
    Subclasses: ChatGraphEngine, AgentEngine(Phase 2), WorkflowEngine(Phase 2)
    """

    @abstractmethod
    async def run(
        self, messages: list[dict], thread_id: str | None = None
    ) -> dict[str, Any]:
        """Execute graph, return final state"""
        ...

    @abstractmethod
    async def stream(
        self, messages: list[dict], thread_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        """Stream graph execution, yield tokens one by one"""
        ...

    @abstractmethod
    async def get_history(self, thread_id: str) -> list[dict]:
        """Get conversation history"""
        ...
