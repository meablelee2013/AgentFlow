"""
LLM Provider 抽象基类

类继承关系:
```mermaid
classDiagram
    class BaseLLMProvider {
        <<abstract>>
        +model_name: str
        +supports_tools: bool
        +invoke(messages) str
        +stream(messages) AsyncGenerator
        +embed(texts) list
    }
    class DeepSeekProvider {
        +invoke(messages) str
        +stream(messages) AsyncGenerator
    }
    class QwenProvider {
        +invoke(messages) str
        +stream(messages) AsyncGenerator
    }
    class OpenAIProvider {
        +invoke(messages) str
        +stream(messages) AsyncGenerator
    }
    BaseLLMProvider <|-- DeepSeekProvider
    BaseLLMProvider <|-- QwenProvider
    BaseLLMProvider <|-- OpenAIProvider
```

设计模式: **策略模式 (Strategy Pattern)**
    StateGraph 通过切换 Provider 实例来改变 LLM 调用行为，
    无需修改上层代码。所有 Provider 共享相同接口，可互相替换。

使用示例:
```python
# 只需换 provider 参数，其余代码不变
provider = DeepSeekProvider(api_key="...")
provider = QwenProvider(api_key="...")
response = await provider.invoke([{"role": "user", "content": "Hello"}])
```
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseLLMProvider(ABC):
    """LLM Provider 抽象基类

    定义所有 LLM Provider 必须实现的契约。
    类似 Java 的 interface，子类必须 override 所有 @abstractmethod。

    三个核心方法:
        invoke()  → 同步调用，返回完整回答
        stream()  → 流式调用，逐 token yield
        embed()   → 文本向量化，返回 embedding 列表
    """

    model_name: str = ""
    supports_tools: bool = False

    @abstractmethod
    async def invoke(self, messages: list[dict]) -> str:
        """调用 LLM，返回完整响应"""
        ...

    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """流式调用 LLM，逐 token yield"""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化，返回 embedding 向量列表"""
        ...
