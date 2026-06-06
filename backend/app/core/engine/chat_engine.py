"""
ChatGraphEngine — 对话引擎

基于 LangGraph StateGraph 的对话引擎，实现:
    1. 多轮对话（messages 使用 operator.add 累加）
    2. 会话持久化（Checkpointer + thread_id）
    3. 流式输出（astream_events）
    4. 历史恢复（相同 thread_id → 自动加载上下文）

StateGraph 结构:
    START → chat_node → END
                     └→ 条件路由 (Phase 2: intent → tool → rag)

State 设计:
    ChatState(TypedDict):
        messages: Annotated[list[BaseMessage], operator.add]
        └── Reducer: operator.add = 列表拼接（累加模式）
        └── 每个节点的返回 dict 会与已有 state 拼接，不是覆盖
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


# ── State 定义 ──────────────────────────────────────────────


class ChatState(TypedDict):
    """对话状态

    关键设计:
        messages 使用 operator.add reducer
        → 新消息拼接到旧消息列表，不覆盖
        → 这是 conversation memory 的基础
    """
    messages: Annotated[List[BaseMessage], operator.add]


# ── ChatGraphEngine ─────────────────────────────────────────


class ChatGraphEngine:
    """LangGraph 对话引擎

    核心流程:
        1. compile() → 构建 StateGraph + 注入 Checkpointer
        2. invoke(state, config) → 执行图，每次执行产生新 checkpoint
        3. 相同 thread_id → 自动从最新 checkpoint 恢复上下文

    使用示例:
        engine = ChatGraphEngine()
        result = await engine.run([{"role": "user", "content": "Hello"}])
        # 继续同一会话:
        result = await engine.run(
            [{"role": "user", "content": "还记得我吗？"}],
            thread_id=result["thread_id"]
        )
    """

    def __init__(self):
        self._graph = self._build_graph()
        self._checkpointer = CheckpointerManager.get()
        self._app = self._graph.compile(checkpointer=self._checkpointer)

    def _build_graph(self) -> StateGraph:
        """构建对话 StateGraph

        Graph 结构:
            START → chat_node → END
        """
        workflow = StateGraph(ChatState)
        workflow.add_node("chat", self._chat_node)
        workflow.add_edge(START, "chat")
        workflow.add_edge("chat", END)
        return workflow

    async def _chat_node(self, state: ChatState) -> dict:
        """对话节点 — 调用 LLM 生成回复

        Args:
            state: 当前 ChatState, 包含完整消息历史

        Returns:
            dict with "messages" key — operator.add 将其拼接到现有列表
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
        """执行对话，返回完整结果

        Args:
            messages: [{"role": "user", "content": "..."}]
            thread_id: 会话 ID，None 则自动生成新会话

        Returns:
            {
                "thread_id": "uuid-string",
                "messages": [{"role": "...", "content": "..."}, ...],
                "is_new": bool  # 是否新会话
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
        """流式执行对话，逐个 token 推送 SSE 事件

        用法 (FastAPI):
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

        # 流式输出 — astream_events 捕获每个 token
        async for event in self._app.astream_events(input_state, config=config, version="v2"):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content

    async def get_history(self, thread_id: str) -> list[dict]:
        """获取会话的完整消息历史

        Args:
            thread_id: 会话 ID

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
        """将 LangChain message 对象序列化为 dict"""
        result = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                result.append({"role": "assistant", "content": msg.content})
        return result
