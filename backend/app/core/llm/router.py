"""
LLMRouter — intelligent model routing

Auto-selects the best LLM Provider based on message characteristics.

Phase 2 rules (current):
    total_chars > LONG_CONTEXT_CHAR_THRESHOLD  → qwen   (long-context value)
    otherwise                                  → deepseek (default, best value)

Note: the original Phase 2 sketch included "code → moonshot", but no Moonshot
Provider is registered yet (see app/core/llm/factory.py::PROVIDER_REGISTRY),
so routing to it would fail. Re-enable that rule once MoonshotProvider lands.

Design pattern: **Strategy + Chain of Responsibility**
    Each routing rule is an independent handler; match returns, no match passes to next.

Upgrade roadmap:
    Phase 1 → fixed deepseek                                          (done)
    Phase 2 → short msg→deepseek, long ctx→qwen                       (current)
    Phase 3 → real-time cost+latency dynamic routing                  (TODO)
"""


class LLMRouter:
    """Intelligent model router"""

    DEFAULT_PROVIDER = "deepseek"
    LONG_CONTEXT_PROVIDER = "qwen"

    # Char-count proxy for "long context". Cheap to compute and avoids pulling
    # in a tokenizer; refine to real token counts if/when accuracy matters.
    # ~8K chars ≈ 2-3K tokens for mixed CN/EN content — well under DeepSeek's
    # 32K context but a reasonable point to prefer Qwen's long-context pricing.
    LONG_CONTEXT_CHAR_THRESHOLD = 8000

    async def route(self, messages: list[dict]) -> str:
        """Select best Provider based on message content.

        Args:
            messages: OpenAI-style message dicts: [{"role": ..., "content": ...}]

        Returns:
            Registered provider name (must exist in PROVIDER_REGISTRY).
        """
        total_chars = sum(
            len(m.get("content") or "")
            for m in messages
        )

        # Rule 1: long context → qwen
        if total_chars > self.LONG_CONTEXT_CHAR_THRESHOLD:
            return self.LONG_CONTEXT_PROVIDER

        # Rule N+1: fall through to default
        return self.DEFAULT_PROVIDER
