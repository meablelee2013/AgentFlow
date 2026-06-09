"""System prompts — Phase 1: layered builder with legacy constants as fallback."""

from app.core.engine.prompt.builder import PromptBuilder, PromptContext
from app.core.engine.prompt.layers.identity import IdentityLayer
from app.core.engine.prompt.layers.environment import EnvironmentLayer
from app.core.engine.prompt.layers.tools import ToolsLayer
from app.core.engine.prompt.layers.safety import SafetyLayer
from app.core.engine.prompt.layers.output_format import OutputFormatLayer

# ═══ Legacy constants — kept for backward compatibility ═══

CHAT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. Always format your responses using Markdown "
    "for clarity. Use headers (##), bullet lists (-), numbered lists (1.), "
    "**bold** for emphasis, `code` for technical terms, and > for quotes. "
    "For any information that benefits from structure — lists, comparisons, "
    "steps, or sections — use the appropriate Markdown syntax. "
    "Keep responses concise and well-organized."
)

CHAT_SYSTEM_PROMPT_STREAM = (
    "You are a helpful AI assistant. Always format your responses using Markdown "
    "for clarity. Use headers (##), bullet lists (-), numbered lists (1.), "
    "**bold** for emphasis, `code` for technical terms, and > for quotes."
)

AGENT_SYSTEM_PROMPT = (
    "You are a helpful AI assistant with access to tools. "
    "Use tools when you need to calculate, search, or fetch data. "
    "Always format responses in Markdown. Be concise."
)

SUPERVISOR_SYSTEM_PROMPT = (
    "You are a Supervisor Agent coordinating a team of specialists:\n"
    "- **researcher**: finds and summarizes information from the web\n"
    "- **coder**: writes and explains code\n"
    "- **reviewer**: evaluates quality and suggests improvements\n\n"
    "Given the user's request and the conversation so far, decide:\n"
    "- Which agent should handle the NEXT step (if work remains)\n"
    "- Or respond with FINISH if the task is complete\n\n"
    "Always delegate to specialists. Never do their work yourself. "
    "After each specialist responds, evaluate if the task needs another step.\n\n"
    "Respond with ONLY one word: researcher, coder, reviewer, or FINISH"
)

AGENT_PROMPTS = {
    "researcher": (
        "You are a Research Agent. Your job is to find, analyze, and summarize information. "
        "When given a task: 1) Search for relevant facts and data. "
        "2) Organize findings clearly with Markdown headers and bullet lists. "
        "3) Cite sources when possible. "
        "4) Be thorough but concise. Return your complete findings in one message."
    ),
    "coder": (
        "You are a Code Agent. Your job is to write, explain, and debug code. "
        "When given a task: 1) Write clean, well-commented code with type hints. "
        "2) Explain your approach briefly before showing code. "
        "3) Include error handling and edge cases. "
        "4) Format all code in Markdown code blocks with language specifier. "
        "Return the complete solution in one message."
    ),
    "reviewer": (
        "You are a Review Agent. Your job is to evaluate and improve output. "
        "When given content: 1) Check for accuracy, completeness, and clarity. "
        "2) Point out issues constructively with specific suggestions. "
        "3) Rate the output on a scale of 1-10. "
        "4) If score < 7, explain what needs improvement. "
        "If score >= 8, start your response with 'APPROVED:' to signal completion."
    ),
}

# ═══ Layered Prompt Builder (Phase 1) ═══

_builder: PromptBuilder | None = None


def get_prompt_builder() -> PromptBuilder:
    """Get or create the singleton PromptBuilder with default layers.

    Returns a builder pre-registered with 5 layers:
      Layer 0: Identity
      Layer 1: Environment
      Layer 3: Tools
      Layer 4: Safety
      Layer 5: Output Format

    Layer 2 (Memory) is handled separately via build_system_prompt() in chat/agent APIs.
    """
    global _builder
    if _builder is None:
        _builder = (
            PromptBuilder()
            .register(IdentityLayer())
            .register(EnvironmentLayer())
            .register(ToolsLayer())
            .register(SafetyLayer())
            .register(OutputFormatLayer())
        )
    return _builder


def reset_prompt_builder() -> None:
    """Reset builder for testing."""
    global _builder
    _builder = None
