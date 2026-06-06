"""
LLMFactory — Factory pattern for creating Provider instances

Call chain:
```mermaid
sequenceDiagram
    participant Service
    participant LLMFactory
    participant LLMRouter
    participant DeepSeekProvider
    participant QwenProvider

    Service->>LLMFactory: create("auto")
    LLMFactory->>LLMRouter: route(messages)
    LLMRouter-->>LLMFactory: "deepseek"
    LLMFactory->>DeepSeekProvider: new DeepSeekProvider(api_key)
    DeepSeekProvider-->>LLMFactory: provider instance
    LLMFactory-->>Service: provider
    Service->>DeepSeekProvider: invoke(messages)
    DeepSeekProvider-->>Service: response
```

Design pattern: **Registry Pattern + Factory Method**
    Add a new Provider by registering in PROVIDER_REGISTRY only,
    no caller code changes needed.
"""

from app.core.llm.providers.base import BaseLLMProvider
from app.core.llm.providers.deepseek import DeepSeekProvider
from app.core.llm.providers.qwen import QwenProvider

# Provider registry — add one line here for a new Provider
PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "deepseek": DeepSeekProvider,
    "qwen": QwenProvider,
}


class LLMFactory:
    """LLM Provider factory

    Usage:
        factory = LLMFactory()
        provider = factory.create("deepseek")
        response = await provider.invoke([{"role": "user", "content": "Hi"}])
    """

    @staticmethod
    def create(provider_name: str = "deepseek", **kwargs) -> BaseLLMProvider:
        """Create LLM Provider instance

        Args:
            provider_name: deepseek | qwen | (future: openai, moonshot...)
            **kwargs: extra kwargs passed to Provider constructor (e.g. api_key)

        Returns:
            BaseLLMProvider subclass instance

        Raises:
            ValueError: provider_name not in registry
        """
        provider_class = PROVIDER_REGISTRY.get(provider_name)
        if not provider_class:
            available = ", ".join(PROVIDER_REGISTRY.keys())
            raise ValueError(
                f"Unsupported LLM provider: '{provider_name}'. "
                f"Available: {available}"
            )
        return provider_class(**kwargs)

    @staticmethod
    def list_providers() -> list[str]:
        """List all registered Provider names"""
        return list(PROVIDER_REGISTRY.keys())
