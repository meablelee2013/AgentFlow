"""
LLM Provider abstract base class

Class hierarchy:
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

Design pattern: **Strategy Pattern**
    StateGraph switches Provider instances to change LLM behavior
    without modifying upper-layer code. All Providers share the same interface.

Usage example:
```python
# Just swap the provider parameter, everything else stays the same
provider = DeepSeekProvider(api_key="...")
provider = QwenProvider(api_key="...")
response = await provider.invoke([{"role": "user", "content": "Hello"}])
```
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseLLMProvider(ABC):
    """LLM Provider abstract base class

    Defines the contract all LLM Providers must implement.
    Like a Java interface, subclasses must override all @abstractmethod.

    Three core methods:
        invoke()  → synchronous call, returns complete response
        stream()  → streaming call, yields tokens one by one
        embed()   → text vectorization, returns embedding list
    """

    model_name: str = ""
    supports_tools: bool = False

    @abstractmethod
    async def invoke(self, messages: list[dict]) -> str:
        """Call LLM, return complete response"""
        ...

    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        """Stream LLM call, yield tokens one by one"""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Text vectorization, returns list of embedding vectors"""
        ...
