"""PromptBuilder — assembles system prompt from registered layers."""

import inspect
import platform as _platform
from datetime import datetime

import tiktoken

from app.core.engine.prompt.base import BasePromptLayer, PromptContext

# DeepSeek / GPT-4 compatible tokenizer (cl100k_base)
# Each layer's text is encoded with this for accurate token counting.
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


class PromptBuilder:
    """Assemble a multi-layer system prompt from registered layers.

    Layers are sorted by priority (lower = higher priority = kept first).
    When total tokens exceed MAX_PROMPT_TOKENS, layers are trimmed starting
    from the highest priority number (lowest actual priority).

    Priority ordering (0 = never trimmed, 5 = trimmed first):
      0: Identity       — "I am AgentFlow..."
      1: Environment    — "Current date: ..."
      4: Safety         — "DO NOT: ..."
      3: Tools          — Tool descriptions
      2: Memory         — User context
      5: Output Format  — Markdown rules
    """

    MAX_PROMPT_TOKENS = 1500

    def __init__(self):
        self._layers: list[BasePromptLayer] = []

    # ── Layer management ──────────────────────────────────────

    def register(self, layer: BasePromptLayer) -> "PromptBuilder":
        self._layers.append(layer)
        return self

    def unregister(self, name: str) -> "PromptBuilder":
        self._layers = [l for l in self._layers if l.name != name]
        return self

    # ── Build ─────────────────────────────────────────────────

    async def build(self, ctx: PromptContext | None = None) -> str:
        """Build the complete system prompt string."""
        result, _ = await self.build_with_info(ctx)
        return result

    async def build_with_info(
        self, ctx: PromptContext | None = None
    ) -> tuple[str, dict]:
        """Build prompt + return token usage info.

        Returns:
            (prompt_string, {
                "total_tokens": int,
                "max_tokens": int,
                "layer_tokens": {name: int},
                "trimmed": bool,
                "trimmed_layers": [str],  # names of layers that were cut
            })
        """
        if ctx is None:
            ctx = PromptContext(
                current_date=datetime.now().strftime("%Y-%m-%d"),
                platform=_platform.system(),
            )
        if not ctx.current_date:
            ctx.current_date = datetime.now().strftime("%Y-%m-%d")
        if not ctx.platform:
            ctx.platform = _platform.system()

        # ── Step 1: Render all layers that pass condition() ──
        sorted_layers = sorted(self._layers, key=lambda l: l.priority)
        # → [Identity(0), Environment(1), Memory(2), Tools(3), Safety(4), Output(5)]

        rendered: list[dict] = []  # {name, text, tokens, priority}
        for layer in sorted_layers:
            try:
                if not layer.condition(ctx):
                    continue
                if inspect.iscoroutinefunction(layer.render):
                    text = await layer.render(ctx)
                else:
                    text = layer.render(ctx)
                if text.strip():
                    tokens = _count_tokens(text)
                    rendered.append({
                        "name": layer.name,
                        "text": text.strip(),
                        "tokens": tokens,
                        "priority": layer.priority,
                    })
            except Exception:
                continue

        total_before = sum(r["tokens"] for r in rendered)

        # ── Step 2: Token budget — trim if over limit ──
        if total_before <= self.MAX_PROMPT_TOKENS:
            # Within budget — no trimming needed
            parts = rendered
            trimmed_layers = []
        else:
            parts, trimmed_layers = self._apply_token_budget(rendered)

        # ── Step 3: Assemble ──
        prompt = "\n\n".join(r["text"] for r in parts)
        info = {
            "total_tokens": sum(r["tokens"] for r in parts),
            "max_tokens": self.MAX_PROMPT_TOKENS,
            "layer_tokens": {r["name"]: r["tokens"] for r in parts},
            "trimmed": len(trimmed_layers) > 0,
            "trimmed_layers": trimmed_layers,
            "tokens_before_trim": total_before,
        }
        return prompt, info

    # ── Token budget logic ────────────────────────────────────

    def _apply_token_budget(self, rendered: list[dict]) -> tuple[list[dict], list[str]]:
        """Trim layers by priority when total tokens exceed budget.

        Priority rules (0 = highest, never trimmed):
          0: Identity      — 绝对不裁。LLM 忘了自己是谁，行为全乱。
          1: Environment   — 绝对不裁。日期/平台影响回答准确性。
          4: Safety        — 尽量不裁。安全规则是底线。
          3: Tools         — 可压缩。工具描述可以被截断，但不能全丢。
          2: Memory        — 可裁剪。用户上下文可以压缩到 Top 5。
          5: Output Format — 最优先裁。可简化为一句 "Use Markdown"。

        Algorithm:
          按 priority 升序（0,1,2,3,4,5 = 从高优先级到低优先级）遍历。
          每一层：完整文本能放下 → 保留。放不下 → 尝试截断。
          截断也放不下 → 丢弃该层及之后所有层。

        Example:
          Identity(80) + Env(50) + Safety(200) + Tools(400) + Memory(800) + Output(100)
          = 1630 tokens > 1500 budget

          80+50=130 → 130+200=330 → 330+400=730 → 730+800=1530 > 1500!
          Memory 放不下 → 截断 Memory: 800→770. 730+770=1500.
          Output 被 break 丢弃。
          Final: Identity + Env + Safety + Tools + Memory(truncated) = 1500
        """
        # Sort by priority ascending (0 first = highest priority)
        sorted_items = sorted(rendered, key=lambda r: r["priority"])

        kept: list[dict] = []
        trimmed: list[str] = []
        running = 0

        for item in sorted_items:
            name = item["name"]
            tokens = item["tokens"]
            text = item["text"]

            if running + tokens <= self.MAX_PROMPT_TOKENS:
                # Fits entirely — keep
                kept.append(item)
                running += tokens
            else:
                # Too large — try truncation
                available = self.MAX_PROMPT_TOKENS - running
                if available > 30:  # worth truncating (> ~120 chars)
                    truncated_text = _truncate_to_tokens(text, available)
                    truncated_tokens = _count_tokens(truncated_text)
                    kept.append({
                        "name": name,
                        "text": truncated_text,
                        "tokens": truncated_tokens,
                        "priority": item["priority"],
                    })
                    trimmed.append(name)
                    running += truncated_tokens
                else:
                    # Not enough space — drop this and all lower-priority layers
                    trimmed.append(name)
                    for remaining in sorted_items[sorted_items.index(item) + 1:]:
                        trimmed.append(remaining["name"])
                break  # No point continuing — lower-priority layers are dropped

        return kept, trimmed

    # ── Properties ────────────────────────────────────────────

    @property
    def layer_count(self) -> int:
        return len(self._layers)

    @property
    def layer_names(self) -> list[str]:
        return sorted([l.name for l in self._layers])


# ═══════════════════════════════════════════════════════════════
# Token utilities
# ═══════════════════════════════════════════════════════════════

def _count_tokens(text: str) -> int:
    """Accurate token count using DeepSeek/GPT-4 compatible tokenizer."""
    return max(1, len(_TOKENIZER.encode(text)))


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to fit within max_tokens, preserving whole tokens."""
    encoded = _TOKENIZER.encode(text)
    if len(encoded) <= max_tokens:
        return text
    truncated = _TOKENIZER.decode(encoded[:max_tokens])
    return truncated.rstrip() + "..."
