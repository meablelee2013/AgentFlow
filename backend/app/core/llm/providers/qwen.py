"""Qwen (Tongyi Qianwen) Provider — Alibaba Cloud DashScope API (OpenAI-compatible)"""
import os
from typing import AsyncGenerator
from openai import AsyncOpenAI
from app.core.llm.providers.base import BaseLLMProvider


class QwenProvider(BaseLLMProvider):
    """Qwen Provider

    Calls via Alibaba Cloud DashScope's OpenAI-compatible endpoint.
    Models: qwen-turbo (value) / qwen-plus (balanced) / qwen-max (powerful)
    """

    model_name = "qwen-plus"
    supports_tools = True

    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("QWEN_API_KEY"),
            base_url=os.getenv(
                "QWEN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )

    async def invoke(self, messages: list[dict]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
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
        embeddings = []
        for text in texts:
            response = await self.client.embeddings.create(
                model="text-embedding-v3",
                input=text,
            )
            embeddings.append(response.data[0].embedding)
        return embeddings
