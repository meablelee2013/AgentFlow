"""Layer 5: Output Format — "How should I respond?" """

from app.core.engine.prompt.base import BasePromptLayer, PromptContext


class OutputFormatLayer(BasePromptLayer):
    name = "output_format"
    priority = 5
    required = True

    def render(self, ctx: PromptContext) -> str:
        return (
            "## Output Format\n"
            "- Default language: Chinese (use English only if the user "
            "explicitly asks).\n"
            "- Use Markdown for structure: ## headers, - bullet lists, "
            "**bold**, `code`, > quotes.\n"
            "- Code MUST be in ```language blocks with the correct "
            "language specifier.\n"
            "- Use tables for comparison data, numbered lists for "
            "sequential steps.\n"
            "- When you used a tool, briefly mention which one: "
            '"(used calculator)".\n'
            "- Keep responses helpful, accurate, and concise."
        )
