"""
Supervisor Multi-Agent Engine — LangGraph orchestration pattern.

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

Design pattern: **Supervisor Pattern**
    A central "supervisor" agent routes tasks to specialized sub-agents.
    Each sub-agent has a clear domain and returns results to the supervisor.
    The supervisor iterates until the task is complete, then returns FINISH.

StateGraph:
    START → supervisor → conditional_edge
        ├── "researcher" → researcher → supervisor
        ├── "coder" → coder → supervisor
        ├── "reviewer" → reviewer → supervisor
        └── "FINISH" → END
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


class SupervisorState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next: str


# Sub-agent system prompts
AGENT_PROMPTS = {
    "researcher": (
        "You are a Research Agent. Your job is to find, analyze, and summarize information. "
        "When given a task: 1) Search for relevant facts and data. "
        "2) Organize findings clearly with Markdown headers and bullet lists. "
        "3) Cite sources when possible. "
        "4) Be thorough but concise. Return your complete findings in one message."
    ),
    "coder": (
        "You are a Code Agent. Your job is to write, explain, and debug code. "
        "When given a task: 1) Write clean, well-commented code with type hints. "
        "2) Explain your approach briefly before showing code. "
        "3) Include error handling and edge cases. "
        "4) Format all code in Markdown code blocks with language specifier. "
        "Return the complete solution in one message."
    ),
    "reviewer": (
        "You are a Review Agent. Your job is to evaluate and improve output. "
        "When given content: 1) Check for accuracy, completeness, and clarity. "
        "2) Point out issues constructively with specific suggestions. "
        "3) Rate the output on a scale of 1-10. "
        "4) If score < 7, explain what needs improvement. "
        "If score >= 8, start your response with 'APPROVED:' to signal completion."
    ),
}

SUPERVISOR_PROMPT = (
    "You are a Supervisor Agent coordinating a team of specialists:\n"
    "- **researcher**: finds and summarizes information from the web\n"
    "- **coder**: writes and explains code\n"
    "- **reviewer**: evaluates quality and suggests improvements\n\n"
    "Given the user's request and the conversation so far, decide:\n"
    "- Which agent should handle the NEXT step (if work remains)\n"
    "- Or respond with FINISH if the task is complete\n\n"
    "Always delegate to specialists. Never do their work yourself. "
    "After each specialist responds, evaluate if the task needs another step.\n\n"
    "Respond with ONLY one word: researcher, coder, reviewer, or FINISH"
)


class SupervisorEngine:
    """Supervisor pattern multi-agent orchestration.

    The supervisor routes tasks to specialized sub-agents and collects
    results until the task is complete.

    Usage:
        engine = SupervisorEngine()
        result = await engine.run([{"role": "user", "content": "Write a sorting function"}])
    """

    MAX_ITERATIONS = 8  # Prevent infinite loops

    def __init__(self):
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(SupervisorState)

        # Add nodes
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
        # All agents return to supervisor
        for agent in ["researcher", "coder", "reviewer"]:
            workflow.add_edge(agent, "supervisor")

        return workflow

    def _make_agent_node(self, role: str):
        """Factory: create a sub-agent node function."""
        async def agent_node(state: SupervisorState) -> dict:
            llm = ChatOpenAI(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                model="deepseek-chat",
                temperature=0.7,
            )
            prompt = AGENT_PROMPTS[role]
            msgs = [SystemMessage(content=prompt)] + list(state["messages"])
            response = await llm.ainvoke(msgs)
            return {"messages": [response]}
        return agent_node

    async def _supervisor_node(self, state: SupervisorState) -> dict:
        """Supervisor reasoning — decide which agent to delegate to next."""
        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.3,  # Lower temp for routing decisions
        )

        msgs = [SystemMessage(content=SUPERVISOR_PROMPT)] + list(state["messages"])
        response = await llm.ainvoke(msgs)

        decision = (response.content or "").strip().lower()
        # The LLM may return text like "FINISH" or "coder" — extract just the word
        for word in ["finish", "researcher", "coder", "reviewer"]:
            if word in decision:
                return {"next": word.upper() if word == "finish" else word}

        # Check iteration limit
        agent_count = sum(
            1 for m in state["messages"]
            if isinstance(m, AIMessage) and m.content
            and any(role in (m.content or "").lower() for role in ["research", "code", "review"])
        )
        if agent_count >= self.MAX_ITERATIONS:
            return {"next": "FINISH"}

        # Default: send to researcher for general queries
        return {"next": "researcher"}

    @staticmethod
    def _route(state: SupervisorState) -> Literal["researcher", "coder", "reviewer", "FINISH"]:
        return state.get("next", "FINISH")  # type: ignore[return-value]

    # ── Public API ─────────────────────────────────────────

    async def run(
        self, messages: list[dict], thread_id: str | None = None
    ) -> dict[str, Any]:
        is_new = thread_id is None
        tid = thread_id or str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": tid}}

        input_msgs = [HumanMessage(content=m["content"]) for m in messages]
        result = await self._app.ainvoke(
            {"messages": input_msgs}, config=config
        )
        return {
            "thread_id": tid,
            "messages": self._serialize(result["messages"]),
            "is_new": is_new,
        }

    async def stream(
        self, messages: list[dict], thread_id: str | None = None
    ) -> AsyncGenerator[str, None]:
        tid = thread_id or str(uuid.uuid4())
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

    @staticmethod
    def _serialize(messages: list[BaseMessage]) -> list[dict]:
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content or ""})
            elif isinstance(msg, SystemMessage):
                pass  # Skip system prompts
        return result
