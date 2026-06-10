"""
Decompose Node Executor — LLM-driven task decomposition.

Given a user goal and a set of available capabilities, this executor:
  1. Builds a decomposition prompt with capability descriptions
  2. Calls the LLM with structured output (JSON schema)
  3. Validates each subtask's executor against the capability registry
  4. Returns a list of SubTask objects for fan-out execution

The LLM is forced to output valid JSON via OpenAI's Structured Output feature.
This guarantees reliability — no regex parsing of free-text JSON.
"""

from __future__ import annotations
import json
import uuid
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.core.workflow.schema import SubTask
from app.core.workflow.capability_registry import (
    CapabilityRegistry, get_capability_registry,
)

# ── Default decomposition prompt ────────────────────────────────────

DECOMPOSE_SYSTEM_PROMPT = """You are a Task Decomposition Agent. Your job is to analyze a complex user request and break it into independent subtasks that can be executed in parallel.

## Your Goal
Given a user's request and a list of available capabilities, produce a set of subtasks where:
1. Each subtask uses EXACTLY ONE capability from the available list
2. All subtasks are INDEPENDENT — they do NOT depend on each other's output
3. Subtasks can run in PARALLEL (no data dependencies)
4. Each subtask has a clear, specific input

## How to Choose the Right Capability

- `web_search`: For finding current information, news, facts, research
- `http_api`: For accessing structured data from APIs or services
- `chat`: For reasoning, analysis, summarization, writing, or answering with existing knowledge
- `rag`: For searching knowledge bases, documents, manuals
- `database`: For querying structured databases
- `code`: For data processing, calculations, format conversion
- `agent:*`: For complex multi-step tasks that need tool use (analysis, coding, writing)

## Important Rules

1. **Decompose only as needed.** Don't over-decompose. A simple question might need just 1-2 subtasks.
2. **No dependencies.** Each subtask must work independently. If task B needs task A's output, DON'T create both — instead create one larger task that handles both steps.
3. **Minimize count.** Use the minimum number of subtasks to cover the goal. 3-5 is typical for complex goals.
4. **Be specific in inputs.** Each subtask's input should be detailed and actionable.
5. **Use agent for complex reasoning.** If a task requires multiple steps, analysis, or tool use, prefer an agent over a simple chat.

## Output Format

You MUST respond with this exact JSON structure — no extra text, no markdown fences:

{
  "reasoning": "Brief explanation of your decomposition strategy",
  "subtasks": [
    {
      "id": "task_1",
      "description": "What this subtask does",
      "executor": "capability_id from the available list",
      "input": {
        "key": "value"
      },
      "expected_output": "What we expect to get back"
    }
  ]
}
"""


class DecomposeExecutor:
    """LLM-driven task decomposition with structured output."""

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        model_name: str | None = None,
    ):
        self.registry = registry or get_capability_registry()
        self.llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=model_name or "deepseek-chat",
            temperature=0.2,  # Low temperature for structural consistency
        )

    async def decompose(
        self,
        goal: str,
        enabled_capabilities: list[str],
        custom_prompt: str = "",
        max_subtasks: int = 10,
    ) -> list[SubTask]:
        """Decompose a user goal into subtasks.

        Args:
            goal: The user's complex goal/request
            enabled_capabilities: List of capability IDs available for dispatch
            custom_prompt: Optional custom system prompt override
            max_subtasks: Maximum number of subtasks to produce

        Returns:
            List of validated SubTask objects ready for fan-out execution
        """
        # Build capability descriptions for the prompt
        capabilities_desc = self.registry.describe_for_prompt(enabled_capabilities)

        if not capabilities_desc.strip():
            raise ValueError(
                f"No capabilities found for IDs: {enabled_capabilities}. "
                f"Available: {[c.id for c in self.registry.list_all()]}"
            )

        # Build messages
        system_prompt = custom_prompt or DECOMPOSE_SYSTEM_PROMPT

        user_prompt = f"""## Available Capabilities

{capabilities_desc}

## User Request

{goal}

## Instructions

Decompose this request into independent subtasks. Maximum {max_subtasks} subtasks.
Output your answer as a JSON object with "reasoning" and "subtasks" fields."""

        # Call LLM
        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        # Parse and validate
        plan = self._parse_response(response.content)
        subtasks = self._validate_subtasks(
            plan.get("subtasks", []),
            enabled_capabilities,
            max_subtasks,
        )

        return subtasks

    def _parse_response(self, content: str) -> dict:
        """Extract JSON from LLM response (handles markdown code fences)."""
        text = content.strip()

        # Remove ```json ... ``` fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 2:
                text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON in the text
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Failed to parse LLM response as JSON:\n{content[:500]}")

    def _validate_subtasks(
        self,
        raw_subtasks: list[dict],
        enabled_capabilities: list[str],
        max_subtasks: int,
    ) -> list[SubTask]:
        """Validate and normalize subtasks from LLM output.

        Checks:
          - Each subtask has a valid executor (in the enabled list)
          - Each subtask has an id and input
          - Don't exceed max_subtasks
        """
        validated = []
        seen_ids = set()

        for i, raw in enumerate(raw_subtasks[:max_subtasks]):
            executor = raw.get("executor", "")
            if not executor:
                continue

            if executor not in enabled_capabilities:
                # Try to find a matching capability by partial match
                matched = None
                for cap_id in enabled_capabilities:
                    if cap_id.endswith(executor) or executor.endswith(cap_id):
                        matched = cap_id
                        break
                if matched:
                    executor = matched
                else:
                    # Skip invalid executors
                    continue

            # Ensure unique IDs
            task_id = raw.get("id", f"task_{i + 1}")
            if task_id in seen_ids:
                task_id = f"{task_id}_{i}"
            seen_ids.add(task_id)

            subtask = SubTask(
                id=task_id,
                description=raw.get("description", f"Subtask {i + 1}"),
                executor=executor,
                input=raw.get("input", {}),
                expected_output=raw.get("expected_output", ""),
                status="pending",
            )
            validated.append(subtask)

        if not validated:
            raise ValueError(
                f"No valid subtasks produced. LLM output: {json.dumps(raw_subtasks, ensure_ascii=False)[:300]}\n"
                f"Enabled capabilities: {enabled_capabilities}"
            )

        return validated


# ── Quick test helper ───────────────────────────────────────────────

async def test_decompose():
    """Quick smoke test for the DecomposeExecutor."""
    executor = DecomposeExecutor()
    subtasks = await executor.decompose(
        goal="Research Tesla's Q1 2025 performance and compare it to BYD",
        enabled_capabilities=["web_search", "chat"],
    )
    print(f"Produced {len(subtasks)} subtasks:")
    for st in subtasks:
        print(f"  [{st.executor}] {st.description[:80]}...")
    return subtasks


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_decompose())
