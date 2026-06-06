"""
DeepSeek Provider — 适配 DeepSeek Chat API (OpenAI 兼容协议)

调用时序:
```mermaid
sequenceDiagram
    participant Caller
    participant DeepSeekProvider
    participant AsyncOpenAI
    participant DeepSeekAPI

    Caller->>DeepSeekProvider: invoke(messages)
    DeepSeekProvider->>AsyncOpenAI: chat.completions.create(model, messages)
    AsyncOpenAI->>DeepSeekAPI: POST /v1/chat/completions
    DeepSeekAPI-->>AsyncOpenAI: ChatCompletion(response)
    AsyncOpenAI-->>DeepSeekProvider: choices[0].message.content
    DeepSeekProvider-->>Caller: "response text"

    Note over Caller,DeepSeekAPI: stream 模式: chunk.choices[0].delta.content 逐 token 返回
```

DeepSeek 是 AgentFlow 的主力模型:
- 成本: ¥5-10/千次对话 (性价比最高)
- 中文: ⭐⭐⭐⭐⭐
- 速度: ⭐⭐⭐⭐
- 协议: OpenAI 兼容，可直接用 openai SDK
"""

import os
from typing import AsyncGenerator
from openai import AsyncOpenAI
from app.core.llm.providers.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek Chat API Provider

    使用 OpenAI 兼容协议调用 DeepSeek。
    模型列表: deepseek-chat (通用), deepseek-reasoner (推理)
    """

    model_name = "deepseek-chat"
    supports_tools = True

    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv(
                "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
            ),
        )

    async def invoke(self, messages: list[dict]) -> str:
        """同步调用 DeepSeek，返回完整回答"""
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式调用 DeepSeek，逐 token yield

        用法:
            async for token in provider.stream(messages):
                yield f"data: {token}\n\n"  # SSE format
        """
        stream = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化 — Phase 1 使用 DeepSeek embedding

        生产环境建议用专门的 embedding 模型 (如 text-embedding-3)
        """
        embeddings = []
        for text in texts:
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=text,
            )
            embeddings.append(response.data[0].embedding)
        return embeddings
