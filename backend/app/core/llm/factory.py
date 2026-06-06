"""
LLMFactory — 工厂模式创建 Provider 实例

调用链:
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

设计模式: **注册表模式 (Registry Pattern) + 工厂方法 (Factory Method)**
    新增 Provider 只需在 PROVIDER_REGISTRY 中注册，
    无需修改任何调用方代码。
"""

from app.core.llm.providers.base import BaseLLMProvider
from app.core.llm.providers.deepseek import DeepSeekProvider
from app.core.llm.providers.qwen import QwenProvider

# Provider 注册表 — 新增 Provider 在此添加一行即可
PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "deepseek": DeepSeekProvider,
    "qwen": QwenProvider,
}


class LLMFactory:
    """LLM Provider 工厂

    使用方式:
        factory = LLMFactory()
        provider = factory.create("deepseek")
        response = await provider.invoke([{"role": "user", "content": "Hi"}])
    """

    @staticmethod
    def create(provider_name: str = "deepseek", **kwargs) -> BaseLLMProvider:
        """创建 LLM Provider 实例

        Args:
            provider_name: deepseek | qwen | (将来: openai, moonshot...)
            **kwargs: 传递给 Provider 构造函数的参数 (如 api_key)

        Returns:
            BaseLLMProvider 子类实例

        Raises:
            ValueError: provider_name 不在注册表中
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
        """列出所有已注册的 Provider 名称"""
        return list(PROVIDER_REGISTRY.keys())
