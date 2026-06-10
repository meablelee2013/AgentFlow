"""BasePromptLayer — abstract base for all prompt layers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptContext:
    """Context passed to each layer's condition() and render().

    Fields are populated by PromptBuilder before calling each layer.
    Layers can read any field but should only write to their own output.
    """

    # ── Environment ──
    current_date: str = ""
    platform: str = ""

    # ── Memory ──
    memory_context: str = ""  # pre-built by existing build_system_prompt()
    memory_enabled: bool = True

    # ── Tools ──
    tools_description: str = ""  # pre-formatted tool descriptions

    # ── User ──
    user_id: str | None = None
    kb_id: str | None = None
    query: str = ""

    # ── DB session (for Memory layer) ──
    db: Any = None  # AsyncSession, passed through from API endpoints

    # ── Extras ──
    extra: dict[str, Any] = field(default_factory=dict)


class BasePromptLayer(ABC):
    """One layer of the system prompt.

    Subclass and implement:
      - condition(ctx) → bool   (should this layer be injected?)
      - render(ctx) → str      (generate the prompt text)
    """

    name: str = "base"
    priority: int = 99
    required: bool = False  # if True, always injected

    def condition(self, ctx: PromptContext) -> bool:
        """Check if this layer should be included. Override in subclasses."""
        return self.required

    @abstractmethod
    def render(self, ctx: PromptContext) -> str:
        """Generate this layer's prompt text."""
        ...
