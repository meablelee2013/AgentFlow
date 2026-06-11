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
from app.core.llm.router import LLMRouter

# Provider registry — add one line here for a new Provider
PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "deepseek": DeepSeekProvider,
    "qwen": QwenProvider,
}


class LLMFactory:
    """LLM Provider factory

    Two entry points:
        create(name, **kwargs)          → caller picks the Provider explicitly (sync)
        create_auto(messages, **kwargs) → LLMRouter picks the Provider (async)

    Usage:
        # Explicit
        provider = LLMFactory.create("deepseek")
        response = await provider.invoke([{"role": "user", "content": "Hi"}])

        # Auto-routed
        provider = await LLMFactory.create_auto(messages)
        response = await provider.invoke(messages)
    """

    # Lazily instantiated; route() is currently stateless so one shared instance
    # is fine. If Phase 3 routing carries warm caches / circuit-breaker state,
    # this is still the right place to hold it.
    _router: LLMRouter | None = None

    @staticmethod
    def _get_router() -> LLMRouter:
        if LLMFactory._router is None:
            LLMFactory._router = LLMRouter()
        return LLMFactory._router

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
    async def create_auto(
        messages: list[dict], **kwargs
    ) -> BaseLLMProvider:
        """Create a Provider auto-selected by LLMRouter from message content.

        Equivalent to: name = await router.route(messages); create(name, **kwargs)

        Kept separate from create() because route() is async — folding both
        into one function would force every caller to await even when they
        already know the provider name.

        Args:
            messages: OpenAI-style message dicts used for routing decisions.
            **kwargs: forwarded to the chosen Provider's constructor.

        Returns:
            BaseLLMProvider subclass instance.
        """
        provider_name = await LLMFactory._get_router().route(messages)
        return LLMFactory.create(provider_name, **kwargs)

    @staticmethod
    def list_providers() -> list[str]:
        """List all registered Provider names"""
        return list(PROVIDER_REGISTRY.keys())
