"""
Fan-out Scheduler — dynamic parallel execution of subtasks.

Given a list of SubTask objects from the Decompose node, this module
dispatches each subtask to its assigned executor and runs them all in
parallel using asyncio.gather.

Key design decisions:
  - asyncio.gather with return_exceptions=True: one failure doesn't kill others
  - Each subtask is independently timed for observability
  - Unknown executors are gracefully marked as failed (not thrown)
  - Results are collected as {subtask_id: SubTask} dict for Aggregate to consume
"""

from __future__ import annotations
import time
import asyncio
from typing import Any

from app.core.workflow.schema import SubTask
from app.core.workflow.capability_registry import (
    CapabilityRegistry, get_capability_registry,
)


async def execute_fanout(
    subtasks: list[SubTask],
    state: dict[str, Any],
    registry: CapabilityRegistry | None = None,
    timeout_per_task: int = 120,
) -> dict[str, SubTask]:
    """Execute subtasks respecting dependency order.

    Subtasks with no dependencies run in parallel. Subtasks that depend on
    others wait for their prerequisites to complete. Each "level" of the
    dependency graph runs concurrently, levels run sequentially.

    Args:
        subtasks: List of pending SubTask objects
        state: Current ChatState (for context passing to executors)
        registry: Capability registry for executor lookup
        timeout_per_task: Max seconds per subtask (default 120s)

    Returns:
        Dict mapping subtask.id → updated SubTask (status + result or error)
    """
    if not subtasks:
        return {}

    registry = registry or get_capability_registry()

    # Build lookup + dependency graph
    subtask_map: dict[str, SubTask] = {st.id: st for st in subtasks}
    result_map: dict[str, SubTask] = {}
    pending_ids = set(subtask_map.keys())
    completed_ids: set[str] = set()

    async def run_one(st: SubTask) -> SubTask:
        """Execute a single subtask, injecting upstream results into input."""
        start = time.monotonic()

        # Inject outputs from dependencies into this subtask's input
        for dep_id in st.depends_on:
            dep_result = result_map.get(dep_id)
            if dep_result and dep_result.status == "completed" and dep_result.result:
                st.input[f"_{dep_id}_output"] = dep_result.result

        capability = registry.get(st.executor)
        if not capability:
            st.status = "failed"
            st.error = f"Unknown executor: {st.executor}"
            st.duration_ms = int((time.monotonic() - start) * 1000)
            return st

        try:
            st.status = "running"

            if capability.type == "builtin_node":
                result = await asyncio.wait_for(
                    _execute_builtin(st.executor, st.input, state),
                    timeout=timeout_per_task,
                )
            elif capability.type == "agent":
                result = await asyncio.wait_for(
                    _execute_agent(st.executor, st.input, state, capability),
                    timeout=timeout_per_task * 3,
                )
            else:
                st.status = "failed"
                st.error = f"Unknown executor type: {capability.type}"
                st.duration_ms = int((time.monotonic() - start) * 1000)
                return st

            st.status = "completed"
            st.result = result

        except asyncio.TimeoutError:
            st.status = "failed"
            st.error = f"Timeout after {timeout_per_task}s"
        except Exception as e:
            st.status = "failed"
            st.error = str(e)

        st.duration_ms = int((time.monotonic() - start) * 1000)
        return st

    # Topological execution: process level by level
    # Each level = subtasks whose dependencies are all satisfied
    while pending_ids:
        # Find tasks ready to run (all deps satisfied)
        ready = [
            subtask_map[tid] for tid in pending_ids
            if all(dep in completed_ids for dep in subtask_map[tid].depends_on)
        ]

        if not ready:
            # Circular dependency or all remaining deps failed — mark remaining as failed
            for tid in pending_ids:
                st = subtask_map[tid]
                st.status = "failed"
                st.error = "Dependency not satisfied (circular or prerequisite failed)"
                result_map[tid] = st
            break

        # Run all ready tasks in parallel
        batch_results = await asyncio.gather(
            *[run_one(st) for st in ready],
            return_exceptions=True,
        )

        for st in batch_results:
            if isinstance(st, SubTask):
                result_map[st.id] = st
                pending_ids.discard(st.id)
                if st.status == "completed":
                    completed_ids.add(st.id)
    return result_map


async def execute_fanout_sse(
    subtasks: list[SubTask],
    state: dict[str, Any],
    registry: CapabilityRegistry | None = None,
    timeout_per_task: int = 120,
):
    """Execute all subtasks in parallel, yielding SSE progress events.

    Yields:
        Tuples of (event_type, event_data):
        - ("subtask_start", {id, description, executor})
        - ("subtask_done", {id, status: "completed", result, duration_ms})
        - ("subtask_failed", {id, status: "failed", error, duration_ms})
    """
    if not subtasks:
        return

    registry = registry or get_capability_registry()

    async def run_one(st: SubTask):
        """Execute a single subtask and return the event."""
        yield ("subtask_start", {
            "id": st.id,
            "description": st.description,
            "executor": st.executor,
        })

        start = time.monotonic()
        capability = registry.get(st.executor)

        if not capability:
            dur = int((time.monotonic() - start) * 1000)
            yield ("subtask_failed", {
                "id": st.id,
                "status": "failed",
                "executor": st.executor,
                "description": st.description,
                "error": f"Unknown executor: {st.executor}",
                "duration_ms": dur,
                "result": None,
            })
            return

        try:
            if capability.type == "builtin_node":
                result = await asyncio.wait_for(
                    _execute_builtin(st.executor, st.input, state),
                    timeout=timeout_per_task,
                )
            elif capability.type == "agent":
                result = await asyncio.wait_for(
                    _execute_agent(st.executor, st.input, state, capability),
                    timeout=timeout_per_task * 3,
                )
            else:
                raise ValueError(f"Unknown capability type: {capability.type}")

            dur = int((time.monotonic() - start) * 1000)
            yield ("subtask_done", {
                "id": st.id,
                "status": "completed",
                "executor": st.executor,
                "description": st.description,
                "result": result,
                "error": None,
                "duration_ms": dur,
            })

        except asyncio.TimeoutError:
            dur = int((time.monotonic() - start) * 1000)
            yield ("subtask_failed", {
                "id": st.id,
                "status": "failed",
                "executor": st.executor,
                "description": st.description,
                "error": f"Timeout after {timeout_per_task}s",
                "duration_ms": dur,
                "result": None,
            })
        except Exception as e:
            dur = int((time.monotonic() - start) * 1000)
            yield ("subtask_failed", {
                "id": st.id,
                "status": "failed",
                "executor": st.executor,
                "description": st.description,
                "error": str(e),
                "duration_ms": dur,
                "result": None,
            })

    # Run all in parallel, but collect events from each
    tasks = [run_one(st) for st in subtasks]
    # Use an async generator approach: iterate each task's events via as_completed
    pending = {asyncio.ensure_future(_consume_gen(gen)): st
               for gen, st in zip(tasks, subtasks)}

    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for fut in done:
            events = fut.result()
            for event in events:
                yield event


async def _consume_gen(agen):
    """Consume an async generator and return all yielded values as a list."""
    results = []
    async for item in agen:
        results.append(item)
    return results


async def _execute_builtin(
    executor_id: str,
    input_data: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    """Execute a builtin node capability.

    Maps capability_id → actual execution function.
    For now, builtin nodes that aren't connected via edges run as
    lightweight inline executors.
    """
    # Remove the async prefix
    if executor_id == "web_search":
        from app.core.tool.builtins.search_backends import get_search_backend
        backend = get_search_backend()
        query = input_data.get("query", "")
        results = await backend.search(query, max_results=5)
        return {
            "items": [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in results],
            "query": query,
            "count": len(results),
        }

    elif executor_id == "http_api":
        import httpx
        url = input_data.get("url", "")
        method = input_data.get("method", "GET").upper()
        headers = input_data.get("headers", {})
        body = input_data.get("body")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method=method,
                url=url,
                headers={str(k): str(v) for k, v in headers.items()} if headers else None,
                content=body.encode() if body and isinstance(body, str) else None,
            )
        try:
            resp_body = resp.json()
        except Exception:
            resp_body = resp.text[:5000]

        return {
            "status": resp.status_code,
            "body": resp_body,
            "headers": dict(resp.headers),
            "duration_ms": resp.elapsed.total_seconds() * 1000,
        }

    elif executor_id == "chat":
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.config import settings as s

        llm = ChatOpenAI(
            base_url=s.DEEPSEEK_BASE_URL,
            api_key=s.DEEPSEEK_API_KEY,
            model="deepseek-chat",
            temperature=0.7,
        )
        prompt = input_data.get("prompt", input_data.get("query", ""))
        msgs = [HumanMessage(content=prompt)]
        if input_data.get("system_prompt"):
            msgs.insert(0, SystemMessage(content=input_data["system_prompt"]))
        response = await llm.ainvoke(msgs)
        return {"content": response.content}

    elif executor_id == "rag":
        # Placeholder: actual RAG execution needs knowledge base context
        query = input_data.get("query", "")
        return {
            "documents": [],
            "query": query,
            "note": "RAG execution requires knowledge base context — returning empty pending full integration",
        }

    elif executor_id == "database":
        # Placeholder: database execution needs credential + connection pool
        return {
            "row_count": 0,
            "columns": [],
            "note": "Database execution requires credential context — returning empty pending full integration",
        }

    elif executor_id == "code":
        # Placeholder: code execution needs Docker sandbox
        return {
            "output": "",
            "note": "Code execution requires Docker sandbox — returning empty pending full integration",
        }

    else:
        return {"note": f"No inline executor for {executor_id}"}


async def _execute_agent(
    agent_id: str,
    input_data: dict[str, Any],
    state: dict[str, Any],
    capability,
) -> dict[str, Any]:
    """Execute an agent capability using the AgentExecutor."""
    from app.core.workflow.agent_executor import AgentExecutor

    executor = AgentExecutor(capability)
    task = input_data.get("task", str(input_data))
    return await executor.execute(task, state)
