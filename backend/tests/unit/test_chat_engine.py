"""Unit tests for Chat Graph Engine"""
import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage
from app.core.engine.chat_engine import ChatGraphEngine, ChatState


def test_chat_state_structure():
    """ChatState 应有 messages 字段"""
    state = ChatState(messages=[])
    assert "messages" in state


def test_graph_builds_without_error():
    """StateGraph 构建不应抛异常"""
    engine = ChatGraphEngine()
    assert engine._graph is not None
    assert engine._app is not None


@pytest.mark.asyncio
async def test_run_creates_new_thread():
    """run() 无 thread_id 时应创建新会话"""
    with patch.object(ChatGraphEngine, "_chat_node") as mock_node:
        mock_node.return_value = {"messages": [AIMessage(content="Hello!")]}
        engine = ChatGraphEngine()
        result = await engine.run([{"role": "user", "content": "Hi"}])
        assert result["is_new"] is True
        assert len(result["thread_id"]) > 0
        # messages 包含 user + assistant（operator.add 累加）
        assert len(result["messages"]) == 2
        assert result["messages"][1] == {"role": "assistant", "content": "Hello!"}


@pytest.mark.asyncio
async def test_run_reuses_thread():
    """相同 thread_id 应复用会话"""
    with patch.object(ChatGraphEngine, "_chat_node") as mock_node:
        mock_node.return_value = {"messages": [AIMessage(content="Hello!")]}
        engine = ChatGraphEngine()
        result1 = await engine.run([{"role": "user", "content": "First"}])
        result2 = await engine.run(
            [{"role": "user", "content": "Second"}],
            thread_id=result1["thread_id"],
        )
        assert result2["is_new"] is False
        assert result2["thread_id"] == result1["thread_id"]


def test_serialize_messages():
    """_serialize_messages 应将 BaseMessage 转为 dict"""
    engine = ChatGraphEngine()
    from langchain_core.messages import HumanMessage, AIMessage
    messages = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
    ]
    result = engine._serialize_messages(messages)
    assert result == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
