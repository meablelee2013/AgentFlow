"""
DeepSeek Provider — adapter for DeepSeek Chat API (OpenAI-compatible protocol)

Call sequence:
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

    Note over Caller,DeepSeekAPI: stream mode: chunk.choices[0].delta.content yields per token
```

DeepSeek is AgentFlow's primary model:
- Cost: ¥5-10/1K conversations (best value)
- Chinese: excellent
- Speed: fast
- Protocol: OpenAI-compatible, use openai SDK directly
"""

import os
from typing import AsyncGenerator
from openai import AsyncOpenAI
from app.core.llm.providers.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    """DeepSeek Chat API Provider

    Calls DeepSeek via OpenAI-compatible protocol.
    Models: deepseek-chat (general), deepseek-reasoner (reasoning)
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
        """Synchronous call to DeepSeek, returns complete response"""
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Stream call to DeepSeek, yields tokens one by one

        Usage:
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
        """Text vectorization — Phase 1 uses DeepSeek embedding

        Production should use dedicated embedding models (e.g. text-embedding-3)
        """
        embeddings = []
        for text in texts:
            response = await self.client.embeddings.create(
                model=self.model_name,
                input=text,
            )
            embeddings.append(response.data[0].embedding)
        return embeddings
