"""Layer 1: Environment — "Where/when am I?" """

from datetime import datetime

from app.core.engine.prompt.base import BasePromptLayer, PromptContext


class EnvironmentLayer(BasePromptLayer):
    name = "environment"
    priority = 1
    required = True

    def render(self, ctx: PromptContext) -> str:
        date_str = ctx.current_date or datetime.now().strftime("%Y-%m-%d")
        platform_str = ctx.platform or "linux"
        return (
            "## Environment\n"
            f"Current date: {date_str}. "
            f"Platform: {platform_str}."
        )
