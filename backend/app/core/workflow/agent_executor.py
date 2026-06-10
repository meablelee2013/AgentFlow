"""
Agent Executor — ReAct (Reasoning + Acting) loop for Agent-type subtasks.

Unlike builtin nodes that do one thing in one call, agents use a
Think → Act → Observe cycle to handle complex multi-step tasks.

Framework design:
  - Accepts an AgentCapability definition (system_prompt + tools)
  - Runs a ReAct loop with max_iterations guard
  - Returns structured output (final answer + tool call trace)
  - Handles timeouts and max-iteration gracefully

This is a lightweight framework — tools are resolved from the existing
tool registry. Custom agents can be defined by users and registered
via the CapabilityRegistry.
"""

from __future__ import annotations
from typing import Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage, HumanMessage, AIMessage, ToolMessage,
)

from app.config import settings


class AgentExecutor:
    """Execute a ReAct agent for a single subtask.

    The agent receives a task description, reasons about what to do,
    calls tools as needed, and produces a final answer.

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
        """
        Args:
            capability: ExecutorCapability with system_prompt, tools, max_iterations
            model_name: Optional model override
        """
        self.capability = capability
        self.system_prompt = capability.system_prompt or "You are a helpful AI assistant."
        self.tool_names = capability.tools or []
        self.max_iterations = getattr(capability, 'max_iterations', 10)

        self.llm = ChatOpenAI(
            base_url=settings.DEEPSEEK_BASE_URL,
            api_key=settings.DEEPSEEK_API_KEY,
            model=model_name or "deepseek-chat",
            temperature=0.3,
        )

    async def execute(self, task: str, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent on a task using ReAct loop.

        Args:
            task: The task description (from SubTask.input)
            state: Current ChatState for context

        Returns:
            {
                "output": str (final answer),
                "iterations": int,
                "tool_calls": [{"tool": str, "result": any}, ...],
                "partial": bool (True if max iterations reached),
            }
        """
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Task: {task}\n\nComplete this task step by step. "
                                f"You have access to these tools: {', '.join(self.tool_names) or 'none'}.\n"
                                f"Provide your final answer when done."),
        ]
        tool_call_log: list[dict] = []

        for iteration in range(1, self.max_iterations + 1):
            response = await self.llm.ainvoke(messages)
            messages.append(response)

            # Check if LLM wants to use tools
            if hasattr(response, 'tool_calls') and response.tool_calls:
                for tc in response.tool_calls:
                    tool_result = await self._execute_tool(tc)
                    tool_msg = ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tc.get("id", str(iteration)),
                    )
                    messages.append(tool_msg)
                    tool_call_log.append({
                        "tool": tc.get("name", "unknown"),
                        "args": tc.get("args", {}),
                        "result": tool_result,
                    })
            else:
                # Final answer — LLM didn't call any tools
                return {
                    "output": response.content if hasattr(response, 'content') else str(response),
                    "iterations": iteration,
                    "tool_calls": tool_call_log,
                    "partial": False,
                }

        # Max iterations reached — return best available answer
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
        }

    async def _execute_tool(self, tool_call: dict) -> str:
        """Execute a single tool call.

        Resolves tools from the existing tool registry.
        Falls back to a descriptive message if tool is not available.
        """
        tool_name = tool_call.get("name", "")
        tool_args = tool_call.get("args", {})

        # Try to use the existing tool system
        try:
            from app.core.tool.registry import get_tool_registry
            tool_registry = get_tool_registry()
            tool = tool_registry.get(tool_name)
            if tool:
                result = await tool.ainvoke(tool_args)
                return str(result)
        except (ImportError, Exception):
            pass

        # Fallback for builtin tools
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
