"""
ChatGraphEngine — Conversation engine

LangGraph StateGraph-based conversation engine, implements:
    1. Multi-turn conversation (messages use operator.add for accumulation)
    2. Session persistence (Checkpointer + thread_id)
    3. Streaming output (astream_events)
    4. History recovery (same thread_id → auto-loads context)

StateGraph structure:
    START → chat_node → END
                     └→ conditional routing (Phase 2: intent → tool → rag)

State design:
    ChatState(TypedDict):
        messages: Annotated[list[BaseMessage], operator.add]
        └── Reducer: operator.add = list concatenation (accumulation mode)
        └── each node's returned dict is concatenated with existing state, not overwritten
"""

import uuid
from typing import Any, AsyncGenerator, TypedDict, Annotated, List
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.core.llm.factory import LLMFactory
from app.core.engine.checkpoint import CheckpointerManager


# ── State definition ──────────────────────────────────────────────


class ChatState(TypedDict):
    """Conversation state

    Key design:
        messages uses operator.add reducer
        → new messages concatenated to existing list, not overwritten
        → this is the foundation of conversation memory
    """
    messages: Annotated[List[BaseMessage], operator.add]


# ── ChatGraphEngine ─────────────────────────────────────────


class ChatGraphEngine:
    """LangGraph Conversation engine

    Core flow:
        1. compile() → builds StateGraph + injects Checkpointer
        2. invoke(state, config) → executes graph, each execution creates new checkpoint
        3. Same thread_id → auto-recovers context from latest checkpoint

    Usage example:
        engine = ChatGraphEngine()
        result = await engine.run([{"role": "user", "content": "Hello"}])
        # continue same session:
        result = await engine.run(
            [{"role": "user", "content": "Remember me?"}],
            thread_id=result["thread_id"]
        )
    """

    def __init__(self):
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)

    def _build_graph(self) -> StateGraph:
        """Build conversation StateGraph

        Graph structure:
            START → chat_node → END
        """
        workflow = StateGraph(ChatState)
        workflow.add_node("chat", self._chat_node)
        workflow.add_edge(START, "chat")
        workflow.add_edge("chat", END)
        return workflow

    async def _chat_node(self, state: ChatState) -> dict:
        """Chat node — calls LLM to generate response

        Args:
            state: Current ChatState, containing full message history

        Returns:
            dict with "messages" key — operator.add appends to existing list
        """
        provider = LLMFactory.create("deepseek")
        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.7,
        )
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}

    # ── Public API ─────────────────────────────────────────

    async def run(
        self,
        messages: list[dict],
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute conversation, return complete result

        Args:
            messages: [{"role": "user", "content": "..."}]
            thread_id: Session ID, None creates a new session

        Returns:
            {
                "thread_id": "uuid-string",
                "messages": [{"role": "...", "content": "..."}, ...],
                "is_new": bool  # whether new session
            }
        """
        is_new = thread_id is None
        tid = thread_id or str(uuid.uuid4())

        config: RunnableConfig = {
            "configurable": {"thread_id": tid}
        }

        input_state = {
            "messages": [HumanMessage(content=m["content"]) for m in messages]
            if messages else []
        }

        result = await self._app.ainvoke(input_state, config=config)

        return {
            "thread_id": tid,
            "messages": self._serialize_messages(result["messages"]),
            "is_new": is_new,
        }

    async def stream(
        self,
        messages: list[dict],
        thread_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream conversation, push SSE events token by token

        Usage (FastAPI):
            async def chat_stream():
                async for token in engine.stream(messages):
                    yield f"data: {token}\n\n"
            return StreamingResponse(chat_stream(), media_type="text/event-stream")
        """
        is_new = thread_id is None
        tid = thread_id or str(uuid.uuid4())

        config: RunnableConfig = {
            "configurable": {"thread_id": tid}
        }

        input_state = {
            "messages": [HumanMessage(content=m["content"]) for m in messages]
            if messages else []
        }

        # streaming output — astream_events captures each token
        async for event in self._app.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

    async def get_history(self, thread_id: str) -> list[dict]:
        """Get complete message history for a session

        Args:
            thread_id: Session ID

        Returns:
            [{"role": "user", "content": "..."}, ...]
        """
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id}
        }
        state = self._app.get_state(config)
        if state.values:
            return self._serialize_messages(state.values.get("messages", []))
        return []

    def _serialize_messages(self, messages: list[BaseMessage]) -> list[dict]:
        """Serialize LangChain message objects to dicts"""
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
        return result
