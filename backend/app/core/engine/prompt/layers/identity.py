"""Layer 0: Identity — "Who am I?" """

from app.core.engine.prompt.base import BasePromptLayer, PromptContext


class IdentityLayer(BasePromptLayer):
    name = "identity"
    priority = 0
    required = True

    def render(self, ctx: PromptContext) -> str:
        return (
            "## Identity\n"
            "You are AgentFlow, an AI Agent platform assistant. "
            "Your role is to help users solve problems through step-by-step "
            "reasoning and tool use. "
            "You operate inside a FastAPI backend, serving chat, agent, "
            "knowledge retrieval, and workflow orchestration requests."
        )
