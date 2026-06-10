"""
Workflow DSL → LangGraph StateGraph Compiler.

Converts the visual workflow JSON definition into an executable LangGraph graph.

Compilation steps:
    1. Parse nodes → create LangGraph node functions
    2. Parse edges → create connections (normal + conditional)
    3. Set entry point (START → first node)
    4. Set finish points (last nodes → END)
    5. Compile with Checkpointer

Data flow (Coze-style):
    Each node:
      1. Resolve declared `inputs` from upstream `node_outputs` → args dict
      2. Call type-specific handler(args, config, state)
      3. Handler returns a dict of structured output
      4. Write to node_outputs[node_id] + append AIMessage summary

```mermaid
flowchart LR
    A[Workflow JSON] --> B[Parser: Schema Validation]
    B --> C[Compiler: DSL → StateGraph]
    C --> D[Inject Checkpointer]
    D --> E[Compile → Runnable]
```
"""

from typing import Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.workflow.schema import WorkflowDefinition, WorkflowNode
from app.core.workflow.template import resolve_inputs
from app.core.engine.chat_engine import ChatState


class WorkflowCompiler:
    """Compile a WorkflowDefinition into an executable LangGraph app."""

    def compile(
        self,
        workflow: WorkflowDefinition,
        checkpointer: BaseCheckpointSaver | None = None,
    ):
        """Compile workflow DSL into a LangGraph runnable.

        Args:
            workflow: The validated workflow definition
            checkpointer: Optional checkpointer for persistence

        Returns:
            Compiled LangGraph app (callable with .ainvoke())
        """
        graph = StateGraph(ChatState)

        # Register nodes
        for node in workflow.nodes:
            graph.add_node(node.id, self._make_node_func(node))

        # Register edges
        for edge in workflow.edges:
            source_node = workflow.get_node(edge.source)
            if source_node and source_node.type == "condition":
                # Conditional edge: use a routing function
                graph.add_conditional_edges(
                    edge.source,
                    self._make_condition_func(source_node),
                    {
                        edge.source_handle or "true": edge.target,
                    }
                )
            else:
                graph.add_edge(edge.source, edge.target)

        # Set entry point
        start_node = workflow.get_start_node()
        if start_node:
            graph.add_edge(START, start_node.id)

        # Auto-connect END: any node with no outgoing edges → END
        for node in workflow.nodes:
            if node.type == "end":
                graph.add_edge(node.id, END)
            elif not workflow.get_outgoing(node.id) and node.type != "end":
                graph.add_edge(node.id, END)

        return graph.compile(checkpointer=checkpointer)

    def _make_node_func(self, node: WorkflowNode):
        """Create a LangGraph node function from a workflow node definition.

        Each node function:
          1. Resolves declared inputs from upstream node_outputs → args
          2. Calls the type-specific handler
          3. Writes output to node_outputs[node_id]
          4. Appends an AIMessage summary for LLM context
        """
        node_id = node.id
        node_type = node.type
        node_inputs = node.inputs
        node_data = node.data

        # ── Node handlers ──────────────────────────────────────

        async def start_func(state: ChatState) -> dict:
            """Start node — map user input into node_outputs."""
            last_msg = state["messages"][-1].content if state["messages"] else ""
            output_name = node_data.get("output_name", "query")
            output = {output_name: last_msg}

            # If start node defines input_params, try to parse structured input
            if node_data.get("input_params"):
                output["params"] = node_data["input_params"]

            return {
                "node_outputs": {node_id: output},
                "messages": [],
            }

        async def chat_func(state: ChatState) -> dict:
            args = resolve_inputs(node_inputs, state)
            llm = ChatOpenAI(
                base_url=settings.DEEPSEEK_BASE_URL,
                api_key=settings.DEEPSEEK_API_KEY,
                model="deepseek-chat", temperature=0.7,
            )
            prompt = node_data.get("system_prompt", "")
            msgs = list(state["messages"])
            if prompt:
                from langchain_core.messages import SystemMessage
                msgs.insert(0, SystemMessage(content=prompt))

            # Inject resolved args as context if any
            if args:
                import json
                args_context = f"\n\nContext from previous nodes:\n{json.dumps(args, ensure_ascii=False, default=str)}"
                msgs.append(HumanMessage(content=args_context))

            response = await llm.ainvoke(msgs)
            return {
                "node_outputs": {node_id: {"content": response.content}},
                "messages": [response],
            }

        async def rag_func(state: ChatState) -> dict:
            args = resolve_inputs(node_inputs, state)
            kb_id = node_data.get("knowledge_base_id", "")
            query = args.get("query", state["messages"][-1].content if state["messages"] else "")
            result_text = f"[RAG search in KB {kb_id[:8]}...]: results for '{query[:50]}...'"
            return {
                "node_outputs": {node_id: {"documents": [], "kb_id": kb_id, "query": query}},
                "messages": [AIMessage(content=result_text)],
            }

        async def tool_func(state: ChatState) -> dict:
            args = resolve_inputs(node_inputs, state)
            tool_name = node_data.get("tool_name", "")
            result_text = f"[Tool: {tool_name} executed]"
            return {
                "node_outputs": {node_id: {"tool_name": tool_name, "result": result_text}},
                "messages": [AIMessage(content=result_text)],
            }

        async def hitl_func(state: ChatState) -> dict:
            args = resolve_inputs(node_inputs, state)
            msg = node_data.get("approval_message", "Approve?")
            result_text = f"[HITL: {msg} — awaiting approval]"
            return {
                "node_outputs": {node_id: {"status": "awaiting_approval", "message": msg}},
                "messages": [AIMessage(content=result_text)],
            }

        async def search_func(state: ChatState) -> dict:
            """Execute web search and return results."""
            args = resolve_inputs(node_inputs, state)
            from app.core.tool.builtins.search_backends import get_search_backend
            query = args.get("query", state["messages"][-1].content if state["messages"] else "")
            backend = get_search_backend()
            results = await backend.search(query, max_results=5)

            if not results:
                result_text = f"No results found for '{query[:100]}...'"
                return {
                    "node_outputs": {node_id: {"results": [], "query": query, "backend": backend.name}},
                    "messages": [AIMessage(content=result_text)],
                }

            lines = [f"Web search results for '{query[:100]}...' (via {backend.name}):\n"]
            search_data = []
            for i, r in enumerate(results):
                lines.append(f"{i + 1}. {r.to_llm_text()}")
                search_data.append({"title": r.title, "url": r.url, "snippet": r.snippet})

            return {
                "node_outputs": {node_id: {"results": search_data, "query": query, "backend": backend.name}},
                "messages": [AIMessage(content="\n\n".join(lines))],
            }

        # ── New business connector nodes ──────────────────────

        async def http_api_func(state: ChatState) -> dict:
            """HTTP API node — call external APIs with authentication."""
            from app.core.workflow.nodes.http_api import http_api_handler
            args = resolve_inputs(node_inputs, state)
            try:
                output = await http_api_handler(args, node_data, state)
                summary = f"HTTP {output.get('status', '?')} from {node_data.get('url', '?')}"
                return {
                    "node_outputs": {node_id: output},
                    "messages": [AIMessage(content=summary)],
                }
            except Exception as e:
                error_output = {"error": str(e), "status": None}
                return {
                    "node_outputs": {node_id: error_output},
                    "messages": [AIMessage(content=f"HTTP API error: {e}")],
                }

        async def database_func(state: ChatState) -> dict:
            """Database node — query PostgreSQL / MySQL."""
            from app.core.workflow.nodes.database import database_handler
            args = resolve_inputs(node_inputs, state)
            try:
                output = await database_handler(args, node_data, state)
                row_count = output.get("row_count", 0)
                summary = f"Database query returned {row_count} rows"
                return {
                    "node_outputs": {node_id: output},
                    "messages": [AIMessage(content=summary)],
                }
            except Exception as e:
                error_output = {"error": str(e), "row_count": 0}
                return {
                    "node_outputs": {node_id: error_output},
                    "messages": [AIMessage(content=f"Database error: {e}")],
                }

        async def code_func(state: ChatState) -> dict:
            """Code node — execute Python in Docker sandbox."""
            from app.core.workflow.nodes.code import code_handler
            args = resolve_inputs(node_inputs, state)
            try:
                output = await code_handler(args, node_data, state)
                summary = "Code executed successfully"
                return {
                    "node_outputs": {node_id: output},
                    "messages": [AIMessage(content=summary)],
                }
            except Exception as e:
                error_output = {"error": str(e)}
                return {
                    "node_outputs": {node_id: error_output},
                    "messages": [AIMessage(content=f"Code execution error: {e}")],
                }

        async def pass_func(state: ChatState) -> dict:
            return {}

        # ── Handler dispatch ───────────────────────────────────

        handlers = {
            "start": start_func,
            "chat": chat_func,
            "search": search_func,
            "rag": rag_func,
            "tool": tool_func,
            "hitl": hitl_func,
            "http_api": http_api_func,
            "database": database_func,
            "code": code_func,
            "end": pass_func,
            "condition": pass_func,
            "loop": pass_func,
        }
        return handlers.get(node_type, pass_func)

    @staticmethod
    def _make_condition_func(node: WorkflowNode):
        """Create a routing function for a condition node."""
        field = node.data.get("field", "")
        operator = node.data.get("operator", "contains")
        value = node.data.get("value", "")
        true_branch = node.data.get("true_branch", "")
        false_branch = node.data.get("false_branch", "")

        def route(state: ChatState) -> str:
            if not state["messages"]:
                return false_branch or "end"
            last = state["messages"][-1].content or ""

            if operator == "contains":
                match = value.lower() in last.lower()
            elif operator == "equals":
                match = last.strip().lower() == value.lower().strip()
            elif operator == "gt":
                try:
                    match = float(last) > float(value)
                except ValueError:
                    match = False
            elif operator == "lt":
                try:
                    match = float(last) < float(value)
                except ValueError:
                    match = False
            else:
                match = False

            return true_branch if match else (false_branch or "end")

        return route
