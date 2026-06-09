"""PromptBuilder — assembles system prompt from registered layers."""

import platform as _platform
from datetime import datetime

from app.core.engine.prompt.base import BasePromptLayer, PromptContext


class PromptBuilder:
    """Assemble a multi-layer system prompt from registered layers.

    Usage:
        builder = PromptBuilder()
        builder.register(IdentityLayer())
        builder.register(EnvironmentLayer())
        # ... register more layers ...

        prompt = await builder.build(ctx)
    """

    def __init__(self):
        self._layers: list[BasePromptLayer] = []

    def register(self, layer: BasePromptLayer) -> "PromptBuilder":
        """Register a layer. Layers are sorted by priority on build()."""
        self._layers.append(layer)
        return self

    def unregister(self, name: str) -> "PromptBuilder":
        """Remove a layer by name."""
        self._layers = [l for l in self._layers if l.name != name]
        return self

    async def build(self, ctx: PromptContext | None = None) -> str:
        """Build the complete system prompt.

        Args:
            ctx: Optional pre-built context. If None, a minimal default is used.

        Returns:
            Assembled system prompt string, layers joined by double newlines.
        """
        if ctx is None:
            ctx = PromptContext(
                current_date=datetime.now().strftime("%Y-%m-%d"),
                platform=_platform.system(),
            )

        # Fill defaults if not provided
        if not ctx.current_date:
            ctx.current_date = datetime.now().strftime("%Y-%m-%d")
        if not ctx.platform:
            ctx.platform = _platform.system()

        # Sort by priority
        sorted_layers = sorted(self._layers, key=lambda l: l.priority)

        parts: list[str] = []
        for layer in sorted_layers:
            try:
                if layer.condition(ctx):
                    rendered = layer.render(ctx)
                    if rendered.strip():
                        parts.append(rendered.strip())
            except Exception:
                # A broken layer should not crash the entire prompt build
                continue

        return "\n\n".join(parts)

    @property
    def layer_count(self) -> int:
        return len(self._layers)

    @property
    def layer_names(self) -> list[str]:
        return sorted([l.name for l in self._layers])
