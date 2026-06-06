"""
LLMRouter — intelligent model routing

Auto-selects the best LLM Provider based on message characteristics.
Phase 1: always returns deepseek (upgrade to cost/latency-aware routing later)

Design pattern: **Strategy + Chain of Responsibility**
    Each routing rule is an independent handler; match returns, no match passes to next.

Upgrade roadmap:
    Phase 1 → fixed deepseek
    Phase 2 → short msg→deepseek, long ctx→qwen, code→moonshot
    Phase 3 → real-time cost+latency dynamic routing
"""


class LLMRouter:
    """Intelligent model router"""

    DEFAULT_PROVIDER = "deepseek"

    async def route(self, messages: list[dict]) -> str:
        """Select best Provider based on message content

        Phase 1: always returns deepseek (simplified, upgrade later)
        """
        return self.DEFAULT_PROVIDER
