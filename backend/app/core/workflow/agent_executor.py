"""
Agent Executor — ReAct loop with LoopGuard safety for Agent-type subtasks.

Integrates multi-layer safety:
    Layer 2: max_iterations (from capability or config)
    Layer 3: Token ratio circuit breaker
    Layer 5: Dedup watchdog + confidence scoring
"""

from __future__ import annotations
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage,
)

from app.config import settings
from app.core.engine.loop_guard import LoopGuard, LoopConfig, LoopVerdict
from app.core.metrics import track_llm_call, record_verdict, update_guard_metrics


class AgentExecutor:
    """Execute a ReAct agent for a single subtask with safety guard.

    Usage:
        from app.core.workflow.capability_registry import ExecutorCapability
        cap = ExecutorCapability(
            id="agent:analyst", type="agent",
            system_prompt="You are a data analyst...",
            tools=["calculator", "web_search"],
            max_iterations=10,
        )
        executor = AgentExecutor(cap)
        result = await executor.execute("Analyze Tesla vs BYD Q1 2025", state)
    """

    def __init__(self, capability, model_name: str | None = None):
        self.capability = capability
        self.system_prompt = capability.system_prompt or "You are a helpful AI assistant."
        self.tool_names = capability.tools or []
        self.max_iterations = getattr(capability, 'max_iterations', 10)

        self.llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=model_name or "deepseek-chat",
            temperature=0.3,
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

    async def execute(self, task: str, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent on a task using ReAct loop with LoopGuard.

        Returns:
            {
                "output": str (final answer),
                "iterations": int,
                "tool_calls": [{"tool": str, "result": any}, ...],
                "partial": bool (True if stopped by safety guard),
                "stop_reason": str | None (LoopVerdict value if stopped),
            }
        """
        guard = LoopGuard(
            config=LoopConfig(
                max_iterations=self.max_iterations,
                context_window=settings.CONTEXT_WINDOW,
                max_output_tokens=settings.MAX_OUTPUT_TOKENS,
                token_warn_ratio=settings.TOKEN_WARN_RATIO,
                token_stop_ratio=settings.TOKEN_STOP_RATIO,
                dedup_window=settings.DEDUP_WINDOW,
                confidence_threshold=settings.CONFIDENCE_THRESHOLD,
                low_confidence_streak=settings.LOW_CONFIDENCE_STREAK,
            ),
            thread_id=task[:50],  # Use task prefix as pseudo-thread-id
        )

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Task: {task}\n\nComplete this task step by step. "
                                f"You have access to these tools: {', '.join(self.tool_names) or 'none'}.\n"
                                f"Provide your final answer when done."),
        ]
        tool_call_log: list[dict] = []

        for iteration in range(1, self.max_iterations + 1):
            @track_llm_call(model="deepseek-chat", provider="deepseek")
            async def _invoke():
                return await self.llm.ainvoke(messages)

            response = await _invoke()
            messages.append(response)

            # Record token usage
            if hasattr(response, "response_metadata"):
                usage = response.response_metadata.get("token_usage", {})
                guard.record_token_usage(usage)
            elif hasattr(response, "usage_metadata"):
                guard.record_token_usage(response.usage_metadata)

            # Estimate input tokens for guard check
            estimated_input = sum(len(m.content) for m in messages) // 4

            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    tool_msg = ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tc.get("id", str(iteration)),
                        name=tc.get("name", "unknown"),
                    )
                    messages.append(tool_msg)
                    tool_call_log.append({
                        "tool": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                        "result": tool_result,
                    })
                    # Record with confidence scoring
                    guard.record_tool_result(str(tool_result))

                # Safety check after tool execution
                tool_results = [str(tc["result"]) for tc in tool_call_log]
                verdict = guard.check(
                    input_tokens=estimated_input,
                    tool_results=tool_results,
                )
                update_guard_metrics(
                    thread_id=task[:50],
                    token_ratio=guard.token_ratio,
                    confidence=guard.avg_confidence,
                    iteration=iteration,
                )
                record_verdict(verdict, thread_id=task[:50], engine="agent_executor")

                if verdict in (
                    LoopVerdict.STOP_MAX_ITERATIONS,
                    LoopVerdict.STOP_TOKEN_BUDGET,
                    LoopVerdict.STOP_DEDUP,
                    LoopVerdict.STOP_LOW_CONFIDENCE,
                ):
                    last_content = ""
                    for msg in reversed(messages):
                        if isinstance(msg, AIMessage) and msg.content:
                            last_content = msg.content
                            break
                    return {
                        "output": last_content or "Agent stopped by safety guard.",
                        "iterations": iteration,
                        "tool_calls": tool_call_log,
                        "partial": True,
                        "stop_reason": verdict.value,
                    }
            else:
                return {
                    "output": response.content if hasattr(response, 'content') else str(response),
                    "iterations": iteration,
                    "tool_calls": tool_call_log,
                    "partial": False,
                    "stop_reason": None,
                }

        # Max iterations reached
        last_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                last_content = msg.content
                break

        return {
            "output": last_content or "Agent reached maximum iterations without producing a final answer.",
            "iterations": self.max_iterations,
            "tool_calls": tool_call_log,
            "partial": True,
            "stop_reason": LoopVerdict.STOP_MAX_ITERATIONS.value,
        }

    async def _execute_tool(self, tool_call: dict) -> str:
        """Execute a single tool call via the tool registry."""
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})

        try:
            from app.core.tool.registry import get_tool_registry
            tool_registry = get_tool_registry()
            tool = tool_registry.get(tool_name)
            if tool:
                result = await tool.ainvoke(tool_args)
                return str(result)
        except (ImportError, Exception):
            pass

        if tool_name == "calculator":
            return await self._calc(tool_args)
        elif tool_name == "web_search":
            return await self._search(tool_args)

        return f"Tool '{tool_name}' is not available. Available tools: {self.tool_names}"

    @staticmethod
    async def _calc(args: dict) -> str:
        """Simple builtin calculator."""
        import ast
        import operator as op

        expr = args.get("expression", args.get("expr", ""))
        if not expr:
            return "Error: no expression provided"

        try:
            allowed = {
                ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
                ast.Div: op.truediv, ast.Pow: op.pow, ast.USub: op.neg,
            }

            def _eval(node):
                if isinstance(node, ast.Expression):
                    return _eval(node.body)
                if isinstance(node, ast.Num):
                    return node.n
                if isinstance(node, ast.BinOp):
                    return allowed[type(node.op)](_eval(node.left), _eval(node.right))
                if isinstance(node, ast.UnaryOp):
                    return allowed[type(node.op)](_eval(node.operand))
                raise ValueError(f"Unsupported: {type(node)}")

            result = _eval(ast.parse(expr, mode='eval'))
            return f"Result: {result}"
        except Exception as e:
            return f"Calculator error: {e}"

    @staticmethod
    async def _search(args: dict) -> str:
        """Execute a web search as a tool."""
        try:
            from app.core.tool.builtins.search_backends import get_search_backend
            backend = get_search_backend()
            query = args.get("query", args.get("q", ""))
            if not query:
                return "Error: no search query"
            results = await backend.search(query, max_results=3)
            if not results:
                return f"No results for '{query}'"
            return "\n".join(
                f"{i + 1}. {r.title}\n   {r.url}\n   {r.snippet[:200]}"
                for i, r in enumerate(results)
            )
        except Exception as e:
            return f"Search error: {e}"
