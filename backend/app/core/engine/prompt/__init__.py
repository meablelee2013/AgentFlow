"""Layered Prompt System — Phase 1

Usage:
    builder = PromptBuilder()
    builder.register(IdentityLayer())
    builder.register(EnvironmentLayer())
    builder.register(ToolsLayer(tool_registry))
    builder.register(SafetyLayer())
    builder.register(OutputFormatLayer())

    context = {"tools_description": "...", "memory_context": "..."}
    system_prompt = await builder.build(context)
"""

from app.core.engine.prompt.builder import PromptBuilder
from app.core.engine.prompt.layers.identity import IdentityLayer
from app.core.engine.prompt.layers.environment import EnvironmentLayer
from app.core.engine.prompt.layers.tools import ToolsLayer
from app.core.engine.prompt.layers.safety import SafetyLayer
from app.core.engine.prompt.layers.output_format import OutputFormatLayer

__all__ = [
    "PromptBuilder",
    "IdentityLayer",
    "EnvironmentLayer",
    "ToolsLayer",
    "SafetyLayer",
    "OutputFormatLayer",
]
