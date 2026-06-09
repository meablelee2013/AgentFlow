"""
AgentGraphEngine — ReAct agent with tool loop.

ReAct (Reasoning + Acting) tool loop:
```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant LLM
    participant ToolRegistry

    User->>Agent: "What is 2+2?"
    Agent->>LLM: invoke(messages + tool schemas)
    LLM-->>Agent: tool_call: calculator("2+2")
    Agent->>ToolRegistry: execute("calculator", expression="2+2")
    ToolRegistry-->>Agent: ToolResult("4")
    Agent->>LLM: invoke(messages + tool_result)
    LLM-->>Agent: "2+2 equals 4"
    Agent-->>User: "2+2 equals 4"

    Note over Agent,LLM: If LLM returns content (no tool_call): loop ends
    Note over Agent,LLM: If LLM returns tool_call: execute → feedback → repeat (max 5 iterations)
```

LangGraph structure:
    START → agent_node → [conditional edge]
        ├── tool_call → tool_node → agent_node (loop)
        └── no tool_call → END
"""

import uuid
from typing import Any, AsyncGenerator, TypedDict, Annotated, List
import operator

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage,
)
from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.core.engine.checkpoint import CheckpointerManager
from app.core.engine.prompts import AGENT_SYSTEM_PROMPT
from langchain_core.tools import BaseTool as LCTool


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]


class AgentGraphEngine:
    """ReAct agent with tool-calling loop.

    The agent iterates between reasoning (LLM) and acting (tools),
    up to a maximum number of iterations before stopping.

    Usage:
        engine = AgentGraphEngine()
        result = await engine.run([{"role": "user", "content": "What is sqrt(144)?"}])
    """

    MAX_TOOL_ITERATIONS = 5

    def __init__(self, tools: list[LCTool] | None = None):
        self.tools = tools or self._default_tools()
        # Build name → tool lookup for execution
        self._tool_map = {t.name: t for t in self.tools}
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)

    @staticmethod
    def _default_tools() -> list[LCTool]:
        """Create default built-in tools (all LangChain BaseTools)."""
        from app.core.tool.builtins.calculator import CalculatorTool
        from app.core.tool.builtins.datetime_tool import DateTimeTool
        from app.core.tool.builtins.web_search import WebSearchTool
        from app.core.tool.builtins.http_request import HTTPRequestTool
        return [CalculatorTool(), DateTimeTool(), WebSearchTool(), HTTPRequestTool()]

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tools", self._tools_node)
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", self._should_continue, {
            "tools": "tools",
            "end": END,
        })
        workflow.add_edge("tools", "agent")
        return workflow

    def _should_continue(self, state: AgentState) -> str:
        """Route: if last message has tool_calls → tools, else end."""
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            # Check iteration limit
            tool_count = sum(
                1 for m in state["messages"]
                if isinstance(m, ToolMessage)
            )
            if tool_count >= self.MAX_TOOL_ITERATIONS:
                return "end"
            return "tools"
        return "end"

    async def _agent_node(self, state: AgentState) -> dict:
        """Agent reasoning node — call LLM with tool schemas."""
        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.7,
        )

        # Bind LangChain tools directly — native function calling
        llm_with_tools = llm.bind_tools(self.tools)

        # Insert system prompt if first message and none already present
        messages = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages.insert(0, SystemMessage(content=AGENT_SYSTEM_PROMPT))

        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    async def _tools_node(self, state: AgentState) -> dict:
        """Execute tool calls via LangChain BaseTool.ainvoke()."""
        last_msg = state["messages"][-1]
        tool_messages = []

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
                result = f"Tool '{tool_name}' not found. Available: {list(self._tool_map.keys())}"
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
        """Run agent with tool access."""
        is_new = thread_id is None
        tid = thread_id or str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": tid}}

        input_messages = [HumanMessage(content=m["content"]) for m in messages]
        if system_prompt:
            input_messages.insert(0, SystemMessage(content=system_prompt))
        result = await self._app.ainvoke(
            {"messages": input_messages}, config=config
        )

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
        """Stream agent execution."""
        tid = thread_id or str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": tid}}
        input_messages = [HumanMessage(content=m["content"]) for m in messages]
        if system_prompt:
            input_messages.insert(0, SystemMessage(content=system_prompt))

        async for event in self._app.astream_events(
            {"messages": input_messages}, config=config, version="v2"
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

    def _serialize_messages(self, messages: list[BaseMessage]) -> list[dict]:
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                item = {"role": "assistant", "content": msg.content or ""}
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    item["tool_calls"] = msg.tool_calls
                result.append(item)
            elif isinstance(msg, ToolMessage):
                result.append({"role": "tool", "content": msg.content, "name": msg.name})
        return result
