"""
Graph Engine 抽象基类

LangGraph 执行生命周期:
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
    Note over StateGraph: 每个 superstep:
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
    """LangGraph 引擎抽象基类

    定义所有 Graph Engine 的契约。
    子类: ChatGraphEngine, AgentEngine(Phase 2), WorkflowEngine(Phase 2)
    """

    @abstractmethod
    async def run(
        self, messages: list[dict], thread_id: str | None = None
    ) -> dict[str, Any]:
        """执行图，返回最终状态"""
        ...

    @abstractmethod
    async def stream(
        self, messages: list[dict], thread_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        """流式执行图，逐 token yield"""
        ...

    @abstractmethod
    async def get_history(self, thread_id: str) -> list[dict]:
        """获取会话历史"""
        ...
