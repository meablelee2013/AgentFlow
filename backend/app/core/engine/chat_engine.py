"""
ChatGraphEngine — Conversation engine with optional tool calling.

When tools are provided, the engine runs a ReAct loop:
```mermaid
sequenceDiagram
    participant User
    participant Chat
    participant LLM
    participant Tool

    User->>Chat: "What's the weather in Beijing?"
    Chat->>LLM: invoke(messages + tool schemas)
    LLM-->>Chat: tool_call: mcp_weather(lat=..., lon=...)
    Chat->>Tool: execute tool
    Tool-->>Chat: result
    Chat->>LLM: invoke(messages + tool_result)
    LLM-->>Chat: "The weather in Beijing is..."
    Chat-->>User: "The weather in Beijing is..."
```

When tools=None (default), the engine uses a simple graph:
    START → chat_node → END

LangGraph structure with tools:
    START → chat_node → [conditional edge]
        ├── tool_call → tools_node → chat_node (loop, max 5 iterations)
        └── no tool_call → END
"""

import os
import uuid
from typing import Any, AsyncGenerator, TypedDict, Annotated
import operator

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool as LCTool

from app.config import settings
from app.core.engine.checkpoint import CheckpointerManager
from app.core.engine.prompts import CHAT_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT_STREAM


# ── State definition ──────────────────────────────────────────────


def _merge_outputs(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge node outputs: new node outputs overwrite same-key entries."""
    return {**left, **right}


class ChatState(TypedDict):
    """Conversation state

    Key design:
        messages uses operator.add reducer
        → new messages concatenated to existing list, not overwritten
        → this is the foundation of conversation memory

        node_outputs uses _merge_outputs reducer
        → each node writes its structured output to node_outputs[node_id]
        → downstream nodes reference upstream data via {{node_x.field}}

    Task decomposition fields (decompose → fan-out → aggregate):
        decomposed_tasks: list of SubTask dicts produced by decompose node
        subtask_results: {subtask_id: SubTask result} from fan-out execution
        execution_trace: full trace with status, durations, errors
    """
    messages: Annotated[list[BaseMessage], operator.add]
    node_outputs: Annotated[dict[str, Any], _merge_outputs]  # workflow node outputs
    decomposed_tasks: list  # list[SubTask] — produced by decompose node
    subtask_results: dict[str, Any]   # {subtask_id: SubTask dict}
    execution_trace: dict | None  # ExecutionTrace dict


# ── ChatGraphEngine ─────────────────────────────────────────


class ChatGraphEngine:
    """LangGraph Conversation engine with optional tool calling.

    Core flow:
        1. compile() → builds StateGraph + injects Checkpointer
        2. invoke(state, config) → executes graph, each execution creates new checkpoint
        3. Same thread_id → auto-recovers context from latest checkpoint

    Usage example:
        # Without tools (backward compatible):
        engine = ChatGraphEngine()
        result = await engine.run([{"role": "user", "content": "Hello"}])

        # With tools (ReAct loop):
        engine = ChatGraphEngine(tools=[weather_tool])
        result = await engine.run([{"role": "user", "content": "Weather in SF?"}])
    """

    MAX_TOOL_ITERATIONS = 5

    def __init__(self, tools: list[LCTool] | None = None):
        self.tools: list[LCTool] = tools or []
        self._tool_map: dict[str, LCTool] = {t.name: t for t in self.tools}
        self._llm = self._create_llm()
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)

    def _create_llm(self) -> ChatOpenAI:
        """Create the LLM instance. Created once in __init__."""
        return ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY"),
            model="deepseek-chat",
            temperature=0.7,
        )

    def _get_llm(self) -> ChatOpenAI:
        """Get the LLM, optionally bound with tools."""
        if self.tools:
            return self._llm.bind_tools(self.tools)
        return self._llm

    def _build_graph(self) -> StateGraph:
        """Build conversation StateGraph.

        Without tools:
            START → chat_node → END

        With tools:
            START → chat_node → [conditional edge]
                ├── tool_call → tools_node → chat_node (loop)
                └── no tool_call → END
        """
        workflow = StateGraph(ChatState)
        workflow.add_node("chat", self._chat_node)
        workflow.add_edge(START, "chat")

        if self.tools:
            workflow.add_node("tools", self._tools_node)
            workflow.add_conditional_edges(
                "chat",
                self._should_continue,
                {
                    "tools": "tools",
                    "end": END,
                },
            )
            workflow.add_edge("tools", "chat")
        else:
            workflow.add_edge("chat", END)

        return workflow

    def _should_continue(self, state: ChatState) -> str:
        """Route: if last message has tool_calls → tools, else end.

        Also enforces MAX_TOOL_ITERATIONS to prevent infinite loops.
        """
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            tool_count = sum(
                1 for m in state["messages"]
                if isinstance(m, ToolMessage)
            )
            if tool_count >= self.MAX_TOOL_ITERATIONS:
                return "end"
            return "tools"
        return "end"

    async def _chat_node(self, state: ChatState) -> dict:
        """Chat node — calls LLM to generate response.

        When tools are bound, the LLM may return tool_calls instead of
        a text response. The conditional edge routes to the tools node.
        """
        llm = self._get_llm()
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}

    async def _tools_node(self, state: ChatState) -> dict:
        """Execute tool calls from the last AIMessage.

        Each tool is looked up in self._tool_map and invoked via
        LangChain's tool.ainvoke(). Results are returned as ToolMessage
        instances that the LLM can use to formulate its final answer.
        """
        last_msg = state["messages"][-1]
        tool_messages: list[ToolMessage] = []

        for tc in last_msg.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool = self._tool_map.get(tool_name)
            if tool:
                try:
                    result = await tool.ainvoke(tool_args)
                except Exception as e:
                    result = f"Error: {e}"
            else:
                result = (
                    f"Tool '{tool_name}' not found. "
                    f"Available: {list(self._tool_map.keys())}"
                )
            tool_messages.append(ToolMessage(
                content=str(result),
                tool_call_id=tc["id"],
                name=tool_name,
            ))

        return {"messages": tool_messages}

    # ── Public API ─────────────────────────────────────────

    async def run(
        self,
        messages: list[dict],
        thread_id: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Execute conversation, return complete result.

        Args:
            messages: [{"role": "user", "content": "..."}]
            thread_id: Session ID, None creates a new session
            system_prompt: Optional override for the system prompt.
                If None, uses the default CHAT_SYSTEM_PROMPT.

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

        input_messages: list[BaseMessage] = [
            HumanMessage(content=m["content"]) for m in messages
        ] if messages else []
        # Prepend system prompt with optional override
        input_messages.insert(
            0,
            SystemMessage(content=system_prompt or CHAT_SYSTEM_PROMPT),
        )
        input_state: dict[str, Any] = {
            "messages": input_messages,
            "node_outputs": {},
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
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream conversation tokens via SSE."""
        tid = thread_id or str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": tid}}
        input_messages: list[BaseMessage] = [
            HumanMessage(content=m["content"]) for m in messages
        ] if messages else []
        input_messages.insert(
            0,
            SystemMessage(content=system_prompt or CHAT_SYSTEM_PROMPT_STREAM),
        )
        input_state: dict[str, Any] = {
            "messages": input_messages,
            "node_outputs": {},
        }

        async for event in self._app.astream_events(
            input_state, config=config, version="v2"
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

    async def get_history(self, thread_id: str) -> list[dict]:
        """Get complete message history for a session.

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
        """Serialize LangChain message objects to dicts.

        Handles: HumanMessage, AIMessage (with optional tool_calls),
        and ToolMessage.
        """
        result: list[dict] = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                item: dict = {"role": "assistant", "content": msg.content or ""}
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    item["tool_calls"] = msg.tool_calls
                result.append(item)
            elif isinstance(msg, ToolMessage):
                result.append({
                    "role": "tool",
                    "content": msg.content,
                    "name": msg.name,
                })
        return result
