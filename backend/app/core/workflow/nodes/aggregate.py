"""
Aggregate Node Executor — collect subtask results and synthesize a final report.

After fan-out execution completes, this executor:
  1. Reads subtask_results from state
  2. Separates completed vs failed subtasks
  3. Builds an LLM prompt with all results
  4. Generates a synthesized final answer
  5. Produces an ExecutionTrace with full observability data

Failure mode (configurable):
  - partial (default): Use whatever results are available, note limitations
  - strict: If any subtask failed, mark the whole aggregation as failed
"""

from __future__ import annotations
import json
import uuid
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from app.config import settings
from app.core.workflow.schema import (
    SubTask, ExecutionTrace, AggregateNodeData,
)

# ── Default aggregation prompt ──────────────────────────────────────

AGGREGATE_SYSTEM_PROMPT = """You are a Report Synthesis Agent. Your job is to combine the results of multiple independent subtasks into a single, coherent, well-structured final answer.

## Input
You will receive:
1. The original user goal
2. Results from each completed subtask
3. Information about any failed subtasks

## Your Task
1. Review all completed subtask results
2. Synthesize everything into a comprehensive final answer
3. If some subtasks failed, note what's missing but work with what you have
4. Format your answer clearly with sections, bullet points, or tables as appropriate

## Output Format
You MUST respond with this JSON structure:

{
  "answer": "Full synthesized answer in Markdown format...",
  "completeness_reason": "Brief note about completeness (e.g., 'All 3 subtasks completed', 'Missing financial data due to API failure')"
}

## Rules
- DO NOT fabricate data from failed subtasks
- If data is limited, be honest about it
- Use Markdown for structure (headers, lists, tables)
- Be thorough but concise
"""

AGGREGATE_STREAM_PROMPT = """You are a Report Synthesis Agent. Combine the results of multiple independent subtasks into a single, coherent, well-structured final answer.

## Rules
- Review all completed subtask results and synthesize them
- If some subtasks failed, note what's missing but work with available data
- DO NOT fabricate data from failed subtasks
- Write your answer DIRECTLY in Markdown — no JSON wrapper, no preamble
- Use headers (##), bullet points, tables as appropriate
- Be thorough but concise
- Start your answer immediately — no "Here is the report" intro
"""


class AggregateExecutor:
    """Collect subtask results and synthesize a final report."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or "deepseek-chat"
        self.llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=self.model_name,
            temperature=0.3,
        )

    async def aggregate_stream(self, goal: str, subtask_results: dict[str, SubTask]):
        """Stream aggregate tokens via async generator for SSE.

        Uses a Markdown-only prompt for clean streaming. Yields token
        strings as the LLM generates them, plus __TRACE__ and __ANSWER__
        sentinel values at the end.
        """
        completed = [st for st in subtask_results.values() if st.status == "completed"]
        failed = [st for st in subtask_results.values() if st.status == "failed"]

        results_text = self._format_results(subtask_results)
        failed_note = ""
        if failed:
            failed_note = "\n## Failed Subtasks\n" + self._format_failed(failed)
            failed_note += "\n\nNote: base your report on available data only. Mention any gaps."

        user_prompt = f"""## Original Goal
{goal}

## Completed Subtask Results
{results_text}
{failed_note}

Synthesize these results into a final answer. Write directly in Markdown."""

        llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=self.model_name,
            temperature=0.3,
            streaming=True,
        )

        full_text = ""
        async for chunk in llm.astream([
            SystemMessage(content=AGGREGATE_STREAM_PROMPT),
            HumanMessage(content=user_prompt),
        ]):
            if chunk.content:
                token = chunk.content
                full_text += token
                yield token

        # Build execution trace
        trace = ExecutionTrace(
            execution_id=str(uuid.uuid4()),
            total=len(subtask_results),
            completed=len(completed),
            failed=len(failed),
            total_duration_ms=0,
            subtasks=sorted(subtask_results.values(), key=lambda s: s.id),
            aggregated_output=full_text,
        )

        yield ("__TRACE__", trace.model_dump())
        yield ("__ANSWER__", full_text)

    async def aggregate(
        self,
        goal: str,
        subtask_results: dict[str, SubTask],
        node_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Aggregate subtask results into a final report + execution trace.

        Args:
            goal: The original user goal/request
            subtask_results: {subtask_id: SubTask} from fan-out execution
            node_data: Aggregate node configuration (failure_mode, summary_prompt)

        Returns:
            {
                "messages": [AIMessage with aggregated output],
                "aggregated_output": str (final report),
                "execution_trace": ExecutionTrace dict,
            }
        """
        config = AggregateNodeData(**(node_data or {}))
        failure_mode = config.failure_mode

        # Separate completed and failed
        subtasks = list(subtask_results.values())
        completed = [st for st in subtasks if st.status == "completed"]
        failed = [st for st in subtasks if st.status == "failed"]

        # Check strict mode
        if failure_mode == "strict" and failed:
            trace = ExecutionTrace(
                execution_id=str(uuid.uuid4()),
                total=len(subtasks),
                completed=len(completed),
                failed=len(failed),
                total_duration_ms=sum(st.duration_ms for st in subtasks),
                subtasks=subtasks,
                aggregated_output="",
            )
            error_msg = (
                f"Aggregation failed (strict mode): {len(failed)}/{len(subtasks)} subtasks failed.\n"
                + "\n".join(f"- {st.id}: {st.error}" for st in failed)
            )
            from langchain_core.messages import AIMessage
            return {
                "messages": [AIMessage(content=error_msg)],
                "aggregated_output": error_msg,
                "execution_trace": trace.model_dump(),
            }

        # Build aggregation prompt
        results_text = self._format_results(subtask_results)
        user_prompt = f"""## Original Goal
{goal}

## Completed Subtask Results
{results_text}

{"## Failed Subtasks" + chr(10) + self._format_failed(failed) if failed else ""}

Synthesize these results into a final answer."""

        # Call LLM for synthesis
        system_prompt = config.summary_prompt or AGGREGATE_SYSTEM_PROMPT

        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            synthesis = self._parse_response(response.content)
        except Exception as e:
            synthesis = {
                "answer": f"Failed to synthesize results: {e}\n\nRaw results:\n{results_text}",
                "completeness_reason": "Synthesis failed",
            }

        # Build execution trace
        trace = ExecutionTrace(
            execution_id=str(uuid.uuid4()),
            total=len(subtasks),
            completed=len(completed),
            failed=len(failed),
            total_duration_ms=sum(st.duration_ms for st in subtasks),
            subtasks=sorted(subtasks, key=lambda s: s.id),
            aggregated_output=synthesis.get("answer", ""),
        )

        answer = synthesis.get("answer", "")
        completeness = synthesis.get("completeness_reason", "")

        # Include trace summary at the end
        trace_summary = (
            f"\n\n---\n📊 **Execution Summary:** "
            f"{trace.completed}/{trace.total} subtasks completed"
            f"{', ' + str(trace.failed) + ' failed' if trace.failed else ''}"
            f" · {trace.total_duration_ms}ms total"
        )
        if completeness:
            trace_summary += f"\n📝 {completeness}"

        final_output = answer + trace_summary

        from langchain_core.messages import AIMessage
        return {
            "messages": [AIMessage(content=final_output)],
            "aggregated_output": answer,
            "execution_trace": trace.model_dump(),
        }

    def _format_results(self, subtask_results: dict[str, SubTask]) -> str:
        """Format subtask results for LLM consumption."""
        parts = []
        for st_id, st in subtask_results.items():
            if st.status != "completed":
                continue
            result_str = json.dumps(st.result, ensure_ascii=False, default=str)
            # Truncate very long results to fit context window
            if len(result_str) > 2000:
                result_str = result_str[:2000] + "...[truncated]"
            parts.append(
                f"### {st.id}: {st.description}\n"
                f"Executor: {st.executor} | Duration: {st.duration_ms}ms\n\n"
                f"{result_str}\n"
            )
        return "\n".join(parts) if parts else "(no completed subtask results)"

    def _format_failed(self, failed: list[SubTask]) -> str:
        """Format failed subtasks for LLM context."""
        return "\n".join(
            f"- **{st.id}** ({st.executor}): {st.error or 'Unknown error'}"
            for st in failed
        )

    def _parse_response(self, content: str) -> dict:
        """Extract JSON from LLM response."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) > 2:
                text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: treat entire response as the answer
            return {"answer": content, "completeness_reason": "LLM returned non-JSON response"}
