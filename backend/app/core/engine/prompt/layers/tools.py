"""Layer 3: Tools — "What can I use?" """

from app.core.engine.prompt.base import BasePromptLayer, PromptContext


_DEFAULT_TOOL_DESCRIPTIONS = """
## Available Tools

- **calculator**: Evaluate math expressions safely.
  Use for: multi-step calculations, formulas, large numbers, unit conversions.
  Don't use for: simple arithmetic you can answer confidently.

- **web_search**: Search the web for real-time or recent information.
  Use for: current events, news, live data, info beyond your knowledge cutoff.
  Don't use for: definitions, textbook knowledge, historical facts.

- **datetime**: Get current date/time or convert timestamps.
  Use for: "what's today's date?", "convert this timestamp".
  Don't use for: date arithmetic (use calculator instead).

- **http_request**: Make HTTP requests to external APIs (GET/POST/PUT/DELETE).
  Use for: fetching data from user-specified public APIs.
  Don't use for: internal services, URLs you don't recognize.

## Tool Usage Rules
1. Use tools only when necessary — if you know the answer, just say it.
2. Independent tool calls can be made together; dependent ones must be sequential.
3. After 5 tool calls without conclusive results, summarize what you know.
4. If a tool fails, explain the error and suggest alternatives.
5. NEVER use http_request on untrusted URLs or internal services.
"""


class ToolsLayer(BasePromptLayer):
    name = "tools"
    priority = 3
    required = True

    def __init__(self, tool_descriptions: str | None = None):
        self._custom = tool_descriptions

    def render(self, ctx: PromptContext) -> str:
        return ctx.tools_description or self._custom or _DEFAULT_TOOL_DESCRIPTIONS
