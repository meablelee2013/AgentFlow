"""
AgentGraphEngine — ReAct agent with tool loop + LoopGuard safety.

ReAct (Reasoning + Acting) tool loop with multi-layer safety:
    Layer 2: Max iteration threshold (configurable via settings.MAX_TOOL_ITERATIONS)
    Layer 3: Token ratio circuit breaker (input_tokens / (context_window - max_output))
    Layer 4: User cancel interface (in-memory cancel registry)
    Layer 5: Dedup watchdog + confidence scoring

LangGraph structure:
    START → agent_node → [conditional edge]
        ├── tool_call → tool_node → agent_node (loop)
        └── no tool_call → END
"""

import uuid
from typing import Any, AsyncGenerator, TypedDict, Annotated, List
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
from app.core.engine.prompts import AGENT_SYSTEM_PROMPT
from app.core.engine.loop_guard import LoopGuard, LoopConfig, LoopVerdict
from app.core.metrics import track_llm_call, record_verdict, update_guard_metrics


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]


class AgentGraphEngine:
    """ReAct agent with tool-calling loop and multi-layer safety guard.

    The agent iterates between reasoning (LLM) and acting (tools),
    protected by LoopGuard against infinite loops, token exhaustion,
    duplicate results, and low-confidence actions.

    Usage:
        engine = AgentGraphEngine()
        result = await engine.run([{"role": "user", "content": "What is sqrt(144)?"}])
    """

    def __init__(self, tools: list[LCTool] | None = None):
        self.tools = tools or self._default_tools()
        self._tool_map = {t.name: t for t in self.tools}
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)
        # Per-thread guard instances (thread_id → LoopGuard)
        self._guards: dict[str, LoopGuard] = {}
        # LoopGuard config from settings
        self._guard_config = LoopConfig(
            max_iterations=settings.MAX_TOOL_ITERATIONS,
            context_window=settings.CONTEXT_WINDOW,
            max_output_tokens=settings.MAX_OUTPUT_TOKENS,
            token_warn_ratio=settings.TOKEN_WARN_RATIO,
            token_stop_ratio=settings.TOKEN_STOP_RATIO,
            dedup_window=settings.DEDUP_WINDOW,
            confidence_threshold=settings.CONFIDENCE_THRESHOLD,
            low_confidence_streak=settings.LOW_CONFIDENCE_STREAK,
        )

    @staticmethod
    def _default_tools() -> list[LCTool]:
        """Create default built-in tools."""
        from app.core.tool.builtins.calculator import CalculatorTool
        from app.core.tool.builtins.datetime_tool import DateTimeTool
        from app.core.tool.builtins.web_search import WebSearchTool
        from app.core.tool.builtins.http_request import HTTPRequestTool
        return [CalculatorTool(), DateTimeTool(), WebSearchTool(), HTTPRequestTool()]

    def _get_guard(self, thread_id: str) -> LoopGuard:
        """Get or create a LoopGuard for the given thread."""
        if thread_id not in self._guards:
            self._guards[thread_id] = LoopGuard(
                config=self._guard_config,
                thread_id=thread_id,
            )
        return self._guards[thread_id]

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
        """Route: if last message has tool_calls → tools, else end.

        Integrates LoopGuard safety checks (Layers 2–5).
        """
        last_msg = state["messages"][-1]
        if not (hasattr(last_msg, "tool_calls") and last_msg.tool_calls):
            return "end"

        # Retrieve the guard for this thread (set in run())
        tid = self._current_thread_id
        guard = self._get_guard(tid)

        # Collect tool results for dedup check
        tool_results = [
            m.content for m in state["messages"]
            if isinstance(m, ToolMessage)
        ]

        # Estimate input tokens from message count (rough heuristic;
        # actual token counts come from LLM response usage and are
        # recorded in _agent_node via record_token_usage)
        estimated_input = sum(
            len(m.content) for m in state["messages"]
            if isinstance(m, (HumanMessage, AIMessage, SystemMessage))
        ) // 4  # ~4 chars per token

        verdict = guard.check(
            input_tokens=estimated_input,
            tool_results=tool_results,
        )

        # Update Prometheus metrics
        update_guard_metrics(
            thread_id=tid,
            token_ratio=guard.token_ratio,
            confidence=guard.avg_confidence,
            iteration=guard.iteration,
        )
        record_verdict(verdict, thread_id=tid, engine="agent")

        if verdict in (
            LoopVerdict.STOP_MAX_ITERATIONS,
            LoopVerdict.STOP_TOKEN_BUDGET,
            LoopVerdict.STOP_DEDUP,
            LoopVerdict.STOP_LOW_CONFIDENCE,
            LoopVerdict.STOP_CANCELLED,
        ):
            return "end"

        # WARN or CONTINUE → proceed with tools
        return "tools"

    async def _agent_node(self, state: AgentState) -> dict:
        """Agent reasoning node — call LLM with tool schemas."""
        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.7,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

        llm_with_tools = llm.bind_tools(self.tools)

        messages = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages.insert(0, SystemMessage(content=AGENT_SYSTEM_PROMPT))

        # Wrap with metrics tracking
        @track_llm_call(model="deepseek-chat", provider="deepseek")
        async def _invoke():
            return await llm_with_tools.ainvoke(messages)

        response = await _invoke()

        # Record actual token usage for Layer 3 (token ratio)
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
            if usage:
                guard = self._get_guard(self._current_thread_id)
                guard.record_token_usage(usage)
        elif hasattr(response, "usage_metadata"):
            usage = response.usage_metadata
            if usage:
                guard = self._get_guard(self._current_thread_id)
                guard.record_token_usage(usage)

        return {"messages": [response]}

    async def _tools_node(self, state: AgentState) -> dict:
        """Execute tool calls and record results with confidence."""
        last_msg = state["messages"][-1]
        guard = self._get_guard(self._current_thread_id)
        tool_messages = []

        for tc in last_msg.tool_calls:
            tool_name = tc["name"]
            tool_args = tc["args"]
            tool = self._tool_map.get(tool_name)
            if tool:
                try:
                    result = await tool.ainvoke(tool_args)
                    result_str = str(result)
                except Exception as e:
                    result_str = f"Error: {e}"
            else:
                result_str = f"Tool '{tool_name}' not found. Available: {list(self._tool_map.keys())}"

            # Record with confidence scoring (Layer 5b)
            guard.record_tool_result(result_str)

            tool_messages.append(ToolMessage(
                content=result_str,
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
        """Run agent with tool access and safety guard.

        Each thread gets its own LoopGuard instance for per-conversation
        tracking of tokens, confidence, and dedup state.
        """
        is_new = thread_id is None
        tid = thread_id or str(uuid.uuid4())

        # Set current thread for guard tracking in graph nodes
        self._current_thread_id = tid
        # Ensure guard exists for this thread
        self._get_guard(tid)

        config: RunnableConfig = {"configurable": {"thread_id": tid}}

        input_messages = [HumanMessage(content=m["content"]) for m in messages]
        if system_prompt:
            input_messages.insert(0, SystemMessage(content=system_prompt))
        result = await self._app.ainvoke(
            {"messages": input_messages, "node_outputs": {}}, config=config
        )

        # Cleanup guard metrics after completion
        guard = self._guards.get(tid)
        if guard:
            LoopGuard.clear_cancel(tid)

        return {
            "thread_id": tid,
            "messages": self._serialize_messages(result["messages"]),
            "is_new": is_new,
            "guard_summary": guard.summary if guard else None,
        }

    async def stream(
        self,
        messages: list[dict],
        thread_id: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream agent execution with safety guard."""
        tid = thread_id or str(uuid.uuid4())
        self._current_thread_id = tid
        self._get_guard(tid)

        config: RunnableConfig = {"configurable": {"thread_id": tid}}
        input_messages = [HumanMessage(content=m["content"]) for m in messages]
        if system_prompt:
            input_messages.insert(0, SystemMessage(content=system_prompt))

        async for event in self._app.astream_events(
            {"messages": input_messages, "node_outputs": {}}, config=config, version="v2"
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

        LoopGuard.clear_cancel(tid)

    def get_guard_summary(self, thread_id: str) -> dict | None:
        """Get the safety guard summary for a thread."""
        guard = self._guards.get(thread_id)
        return guard.summary if guard else None

    def cancel(self, thread_id: str) -> bool:
        """Request cancellation for a running thread (Layer 4)."""
        return LoopGuard.request_cancel(thread_id)

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
