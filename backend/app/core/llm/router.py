"""
LLMRouter — 智能模型路由

根据消息特征自动选择最合适的 LLM Provider。
Phase 1: 默认返回 deepseek（后续升级到成本/延迟感知路由）

设计模式: **策略 + 责任链**
    每个路由规则是独立 handler，匹配则返回，不匹配则传递给下一个规则。

升级路线:
    Phase 1 → 固定 deepseek
    Phase 2 → 短消息→deepseek, 长上下文→qwen, 代码→moonshot
    Phase 3 → 基于实时成本+延迟的动态路由
"""


class LLMRouter:
    """智能模型路由器"""

    DEFAULT_PROVIDER = "deepseek"

    async def route(self, messages: list[dict]) -> str:
        """根据消息内容选择最佳 Provider

        Phase 1: 始终返回 deepseek（简化实现，后续升级）
        """
        return self.DEFAULT_PROVIDER
