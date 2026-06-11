"""Unit tests for LLM Provider layer"""
import pytest
from unittest.mock import AsyncMock, patch
from app.core.llm.providers.deepseek import DeepSeekProvider
from app.core.llm.providers.qwen import QwenProvider
from app.core.llm.factory import LLMFactory
from app.core.llm.router import LLMRouter


@pytest.mark.asyncio
async def test_deepseek_invoke_returns_string():
    """DeepSeek invoke 应返回字符串"""
    provider = DeepSeekProvider(api_key="test-key")
    mock_create = AsyncMock()
    mock_create.return_value = AsyncMock(
        choices=[AsyncMock(message=AsyncMock(content="Hello World"))]
    )
    provider.client.chat.completions.create = mock_create

    result = await provider.invoke([{"role": "user", "content": "Hi"}])
    assert result == "Hello World"


@pytest.mark.asyncio
async def test_deepseek_stream_yields_tokens():
    """DeepSeek stream 应逐 token yield"""
    provider = DeepSeekProvider(api_key="test-key")

    async def mock_stream(*args, **kwargs):
        yield AsyncMock(choices=[AsyncMock(delta=AsyncMock(content="Hello "))])
        yield AsyncMock(choices=[AsyncMock(delta=AsyncMock(content="World"))])

    provider.client.chat.completions.create = AsyncMock(return_value=mock_stream())

    tokens = []
    async for token in provider.stream([{"role": "user", "content": "Hi"}]):
        tokens.append(token)
    assert tokens == ["Hello ", "World"]


def test_deepseek_supports_tools():
    """DeepSeek 应支持 Function Calling"""
    provider = DeepSeekProvider(api_key="test-key")
    assert provider.supports_tools is True


@pytest.mark.asyncio
async def test_qwen_invoke():
    """Qwen invoke 应正常返回"""
    provider = QwenProvider(api_key="test-key")
    provider.client.chat.completions.create = AsyncMock(
        return_value=AsyncMock(
            choices=[AsyncMock(message=AsyncMock(content="你好"))]
        )
    )

    result = await provider.invoke([{"role": "user", "content": "你好"}])
    assert result == "你好"
    assert provider.model_name == "qwen-plus"


def test_factory_create_deepseek():
    """Factory 应创建正确的 Provider 实例"""
    provider = LLMFactory.create("deepseek", api_key="test")
    assert isinstance(provider, DeepSeekProvider)


def test_factory_create_qwen():
    """Factory 应创建 Qwen Provider"""
    provider = LLMFactory.create("qwen", api_key="test")
    assert isinstance(provider, QwenProvider)


def test_factory_create_invalid_raises():
    """不支持的 provider 应抛出 ValueError"""
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMFactory.create("unknown_provider")


def test_factory_list_providers():
    """list_providers 应返回已注册列表"""
    providers = LLMFactory.list_providers()
    assert "deepseek" in providers
    assert "qwen" in providers


# ── LLMRouter (Phase 2) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_router_short_messages_route_to_deepseek():
    """短消息走默认 Provider(deepseek)"""
    router = LLMRouter()
    name = await router.route([{"role": "user", "content": "你好"}])
    assert name == "deepseek"


@pytest.mark.asyncio
async def test_router_long_context_routes_to_qwen():
    """总字符数超过阈值 → 路由到 qwen(长文本性价比)"""
    router = LLMRouter()
    long_text = "x" * (LLMRouter.LONG_CONTEXT_CHAR_THRESHOLD + 1)
    name = await router.route([{"role": "user", "content": long_text}])
    assert name == "qwen"


@pytest.mark.asyncio
async def test_router_sums_chars_across_messages():
    """阈值判定是所有 message.content 加总,不是单条"""
    router = LLMRouter()
    half = "x" * (LLMRouter.LONG_CONTEXT_CHAR_THRESHOLD // 2 + 1)
    name = await router.route([
        {"role": "system", "content": half},
        {"role": "user", "content": half},
    ])
    assert name == "qwen"


@pytest.mark.asyncio
async def test_router_handles_missing_content():
    """缺失或 None 的 content 不应抛错(tool/assistant 消息常见)"""
    router = LLMRouter()
    name = await router.route([
        {"role": "assistant", "content": None},
        {"role": "tool"},  # no content key at all
        {"role": "user", "content": "hi"},
    ])
    assert name == "deepseek"


# ── LLMFactory.create_auto ────────────────────────────────────


@pytest.mark.asyncio
async def test_factory_create_auto_short_returns_deepseek():
    """短消息 create_auto → DeepSeekProvider 实例"""
    provider = await LLMFactory.create_auto(
        [{"role": "user", "content": "Hi"}], api_key="test"
    )
    assert isinstance(provider, DeepSeekProvider)


@pytest.mark.asyncio
async def test_factory_create_auto_long_returns_qwen():
    """长消息 create_auto → QwenProvider 实例"""
    long_text = "x" * (LLMRouter.LONG_CONTEXT_CHAR_THRESHOLD + 1)
    provider = await LLMFactory.create_auto(
        [{"role": "user", "content": long_text}], api_key="test"
    )
    assert isinstance(provider, QwenProvider)
