"""
Supervisor Multi-Agent Engine — LangGraph orchestration with LoopGuard safety.

```mermaid
graph TD
    User --> Supervisor
    Supervisor --> Researcher[Researcher: web search + summarize]
    Supervisor --> Coder[Coder: generate + test code]
    Supervisor --> Reviewer[Reviewer: quality check + feedback]
    Supervisor --> FINISH

    Researcher --> Supervisor
    Coder --> Supervisor
    Reviewer --> Supervisor
```

Protected by LoopGuard against infinite supervisor loops.
"""

import uuid
from typing import Any, AsyncGenerator, TypedDict, Annotated, List, Literal
import operator

from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, SystemMessage,
)
from langchain_core.runnables import RunnableConfig

from app.config import settings
from app.core.engine.checkpoint import CheckpointerManager
from app.core.engine.prompts import (
    SUPERVISOR_SYSTEM_PROMPT as DEFAULT_SUPERVISOR_PROMPT,
    AGENT_PROMPTS as DEFAULT_AGENT_PROMPTS,
)
from app.core.engine.loop_guard import LoopGuard, LoopConfig, LoopVerdict
from app.core.metrics import track_llm_call, record_verdict, update_guard_metrics


class SupervisorState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str


class SupervisorEngine:
    """Supervisor pattern multi-agent orchestration with LoopGuard.

    The supervisor routes tasks to specialized sub-agents and collects
    results until the task is complete, protected against infinite loops.

    Usage:
        engine = SupervisorEngine()
        result = await engine.run([{"role": "user", "content": "Write a sorting function"}])
    """

    def __init__(
        self,
        supervisor_prompt: str | None = None,
        agent_prompts: dict[str, str] | None = None,
    ):
        self.supervisor_prompt = supervisor_prompt or DEFAULT_SUPERVISOR_PROMPT
        self.agent_prompts = agent_prompts or dict(DEFAULT_AGENT_PROMPTS)
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)
        self._guards: dict[str, LoopGuard] = {}
        self._guard_config = LoopConfig(
            max_iterations=settings.MAX_TOOL_ITERATIONS,
            context_window=settings.CONTEXT_WINDOW,
            max_output_tokens=settings.MAX_OUTPUT_TOKENS,
            token_warn_ratio=settings.TOKEN_WARN_RATIO,
            token_stop_ratio=settings.TOKEN_STOP_RATIO,
        )

    def _get_guard(self, thread_id: str) -> LoopGuard:
        if thread_id not in self._guards:
            self._guards[thread_id] = LoopGuard(
                config=self._guard_config,
                thread_id=thread_id,
            )
        return self._guards[thread_id]

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(SupervisorState)

        workflow.add_node("supervisor", self._supervisor_node)
        workflow.add_node("researcher", self._make_agent_node("researcher"))
        workflow.add_node("coder", self._make_agent_node("coder"))
        workflow.add_node("reviewer", self._make_agent_node("reviewer"))

        workflow.add_edge(START, "supervisor")
        workflow.add_conditional_edges("supervisor", self._route, {
            "researcher": "researcher",
            "coder": "coder",
            "reviewer": "reviewer",
            "FINISH": END,
        })
        for agent in ["researcher", "coder", "reviewer"]:
            workflow.add_edge(agent, "supervisor")

        return workflow

    def _make_agent_node(self, role: str):
        """Factory: create a sub-agent node function with timeout."""
        async def agent_node(state: SupervisorState) -> dict:
            llm = ChatOpenAI(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                model="deepseek-chat",
                temperature=0.7,
                timeout=settings.LLM_TIMEOUT_SECONDS,
                max_tokens=settings.LLM_MAX_TOKENS,
            )
            prompt = self.agent_prompts.get(role, DEFAULT_AGENT_PROMPTS.get(role, ""))
            msgs = [SystemMessage(content=prompt)] + list(state["messages"])

            @track_llm_call(model="deepseek-chat", provider="deepseek")
            async def _invoke():
                return await llm.ainvoke(msgs)

            response = await _invoke()
            return {"messages": [response]}
        return agent_node

    async def _supervisor_node(self, state: SupervisorState) -> dict:
        """Supervisor reasoning — decide which agent to delegate to next.

        Integrates LoopGuard: checks iteration limits and token budget
        before making routing decisions.
        """
        tid = getattr(self, '_current_thread_id', '')
        guard = self._get_guard(tid)

        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.3,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

        msgs = [SystemMessage(content=self.supervisor_prompt)] + list(state["messages"])

        @track_llm_call(model="deepseek-chat", provider="deepseek")
        async def _invoke():
            return await llm.ainvoke(msgs)

        response = await _invoke()

        # Record token usage
        if hasattr(response, "response_metadata"):
            usage = response.response_metadata.get("token_usage", {})
            if usage:
                guard.record_token_usage(usage)
        elif hasattr(response, "usage_metadata"):
            guard.record_token_usage(response.usage_metadata)

        decision = (response.content or "").strip().lower()

        # Check LoopGuard before routing
        estimated_input = sum(
            len(m.content) for m in state["messages"]
            if isinstance(m, AIMessage)
        ) // 4
        verdict = guard.check(input_tokens=estimated_input)

        update_guard_metrics(
            thread_id=tid,
            token_ratio=guard.token_ratio,
            confidence=guard.avg_confidence,
            iteration=guard.iteration,
        )
        record_verdict(verdict, thread_id=tid, engine="supervisor")

        if verdict in (
            LoopVerdict.STOP_MAX_ITERATIONS,
            LoopVerdict.STOP_TOKEN_BUDGET,
            LoopVerdict.STOP_CANCELLED,
        ):
            return {"next": "FINISH"}

        # Parse LLM decision
        for word in ["finish", "researcher", "coder", "reviewer"]:
            if word in decision:
                return {"next": word.upper() if word == "finish" else word}

        # Default to FINISH as safety (was: researcher)
        return {"next": "FINISH"}

    @staticmethod
    def _route(state: SupervisorState) -> Literal["researcher", "coder", "reviewer", "FINISH"]:
        return state.get("next", "FINISH")  # type: ignore[return-value]

    # ── Public API ─────────────────────────────────────────

    async def run(
        self, messages: list[dict], thread_id: str | None = None
    ) -> dict[str, Any]:
        is_new = thread_id is None
        tid = thread_id or str(uuid.uuid4())
        self._current_thread_id = tid
        self._get_guard(tid)

        config: RunnableConfig = {"configurable": {"thread_id": tid}}

        input_msgs = [HumanMessage(content=m["content"]) for m in messages]
        result = await self._app.ainvoke(
            {"messages": input_msgs}, config=config
        )

        guard = self._guards.get(tid)
        LoopGuard.clear_cancel(tid)

        return {
            "thread_id": tid,
            "messages": self._serialize(result["messages"]),
            "is_new": is_new,
            "guard_summary": guard.summary if guard else None,
        }

    async def stream(
        self, messages: list[dict], thread_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        tid = thread_id or str(uuid.uuid4())
        self._current_thread_id = tid
        self._get_guard(tid)

        config: RunnableConfig = {"configurable": {"thread_id": tid}}
        input_msgs = [HumanMessage(content=m["content"]) for m in messages]

        async for event in self._app.astream_events(
            {"messages": input_msgs}, config=config, version="v2"
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

        LoopGuard.clear_cancel(tid)

    def cancel(self, thread_id: str) -> bool:
        return LoopGuard.request_cancel(thread_id)

    @staticmethod
    def _serialize(messages: list[BaseMessage]) -> list[dict]:
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content or ""})
            elif isinstance(msg, SystemMessage):
                pass
        return result
