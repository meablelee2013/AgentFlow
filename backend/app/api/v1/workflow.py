"""Workflow API — save, load, list, execute workflows"""
import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
import structlog

from app.api.v1.deps import get_db
from app.core.workflow.schema import WorkflowDefinition, SubTask, ExecutionTrace
from app.core.workflow.compiler import WorkflowCompiler
from app.core.engine.checkpoint import CheckpointerManager

logger = structlog.get_logger()
router = APIRouter(prefix="/workflows", tags=["workflows"])

# In-memory store (Phase 2 — Phase 3 adds PostgreSQL persistence)
_store: dict[str, WorkflowDefinition] = {}
compiler = WorkflowCompiler()


class WorkflowSaveRequest(BaseModel):
    name: str = "Untitled"
    description: str = ""
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    nodes: list[dict]
    edges: list[dict]


class ExecuteRequest(BaseModel):
    message: str


@router.post("", response_model=WorkflowResponse)
async def save_workflow(req: WorkflowSaveRequest):
    """Save a workflow definition."""
    wf = WorkflowDefinition(
        name=req.name,
        description=req.description,
        nodes=[{
            "id": n.get("id", str(uuid.uuid4())),
            "type": n["type"],
            "position": n.get("position", {"x": 0, "y": 0}),
            "inputs": n.get("inputs", []),
            "outputs": n.get("outputs", []),
            "data": n.get("data", {}),
        } for n in req.nodes],
        edges=[{
            "id": e.get("id", str(uuid.uuid4())),
            "source": e["source"],
            "target": e["target"],
            "source_handle": e.get("sourceHandle"),
            "label": e.get("label"),
        } for e in req.edges],
    )
    _store[wf.id] = wf
    return WorkflowResponse(
        id=wf.id, name=wf.name, description=wf.description,
        nodes=[n.model_dump() for n in wf.nodes],
        edges=[e.model_dump() for e in wf.edges],
    )


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows():
    """List all saved workflows."""
    return [
        WorkflowResponse(
            id=wf.id, name=wf.name, description=wf.description,
            nodes=[n.model_dump() for n in wf.nodes],
            edges=[e.model_dump() for e in wf.edges],
        )
        for wf in _store.values()
    ]


@router.get("/{wf_id}", response_model=WorkflowResponse)
async def get_workflow(wf_id: str):
    """Get a workflow by ID."""
    wf = _store.get(wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return WorkflowResponse(
        id=wf.id, name=wf.name, description=wf.description,
        nodes=[n.model_dump() for n in wf.nodes],
        edges=[e.model_dump() for e in wf.edges],
    )


@router.delete("/{wf_id}", status_code=204)
async def delete_workflow(wf_id: str):
    """Delete a workflow."""
    if wf_id in _store:
        del _store[wf_id]


@router.post("/{wf_id}/execute")
async def execute_workflow(wf_id: str, req: ExecuteRequest):
    """Execute a workflow with the given input message.

    Returns the final assistant response.
    """
    wf = _store.get(wf_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    checkpointer = CheckpointerManager.get()
    # Checkpointer is already PG-backed thanks to lifespan ensure_postgres()
    app = compiler.compile(wf, checkpointer=checkpointer)

    from langchain_core.messages import HumanMessage
    result = await app.ainvoke(
        {"messages": [HumanMessage(content=req.message)], "node_outputs": {}},
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    reply = ""
    for m in reversed(result["messages"]):
        if hasattr(m, "content") and m.content:
            reply = m.content
            break

    # Include node_outputs in response for debugging/introspection
    node_outputs = result.get("node_outputs", {})

    # Include execution_trace if the workflow used task decomposition
    execution_trace = result.get("execution_trace", None)
    decomposed_tasks = result.get("decomposed_tasks", [])
    subtask_results = result.get("subtask_results", {})

    return {
        "output": reply,
        "node_outputs": node_outputs,
        "execution_trace": execution_trace,
        "decomposed_tasks": decomposed_tasks,
        "subtask_results": subtask_results,
    }


# ── Test Decompose (no workflow save needed) ────────────────────────


class TestDecomposeRequest(BaseModel):
    goal: str
    enabled_capabilities: list[str] = Field(default_factory=list)  # empty = all builtin
    max_subtasks: int = Field(default=10, ge=1, le=20)


@router.post("/test-decompose")
async def test_decompose(req: TestDecomposeRequest):
    """Test the decompose → fan-out → aggregate pipeline without saving a workflow.

    This is a playground endpoint for testing task decomposition.
    It runs the full pipeline in memory and returns the complete trace.

    Returns:
        {
            "goal": original goal,
            "reasoning": LLM's decomposition reasoning,
            "subtasks": [{id, description, executor, input, status, result, error, duration_ms}, ...],
            "aggregated_output": final synthesized report (Markdown),
            "execution_trace": {total, completed, failed, total_duration_ms},
        }
    """
    from app.core.workflow.capability_registry import get_capability_registry
    from app.core.workflow.nodes.decompose import DecomposeExecutor
    from app.core.workflow.fanout import execute_fanout
    from app.core.workflow.nodes.aggregate import AggregateExecutor

    registry = get_capability_registry()

    # Determine capabilities
    enabled_caps = req.enabled_capabilities
    if not enabled_caps:
        # Default: all builtin capabilities
        enabled_caps = [c.id for c in registry.list_builtin()]

    overall_start = time.monotonic()

    # Step 1: Decompose
    decomposer = DecomposeExecutor()
    try:
        subtasks = await decomposer.decompose(
            goal=req.goal,
            enabled_capabilities=enabled_caps,
            max_subtasks=req.max_subtasks,
        )
        reasoning = "See subtasks below"  # Will be overridden if LLM provides it
    except Exception as e:
        return {
            "goal": req.goal,
            "error": f"Decomposition failed: {e}",
            "subtasks": [],
            "aggregated_output": "",
            "execution_trace": None,
        }

    # Step 2: Fan-out (parallel execution)
    state: dict = {"messages": [], "node_outputs": {}}
    results = await execute_fanout(subtasks, state, registry=registry)

    # Step 3: Aggregate
    aggregator = AggregateExecutor()
    aggregate_result = await aggregator.aggregate(
        goal=req.goal,
        subtask_results=results,
        node_data={"failure_mode": "partial"},
    )

    # Build response
    subtask_list = []
    for st in subtasks:
        executed = results.get(st.id)
        subtask_list.append({
            "id": st.id,
            "description": st.description,
            "executor": st.executor,
            "input": st.input,
            "expected_output": st.expected_output,
            "status": executed.status if executed else "failed",
            "result": executed.result if executed else None,
            "error": executed.error if executed else "Not executed",
            "duration_ms": executed.duration_ms if executed else 0,
        })

    trace = aggregate_result.get("execution_trace", {})
    total_duration_ms = int((time.monotonic() - overall_start) * 1000)
    if isinstance(trace, dict):
        trace["total_duration_ms"] = total_duration_ms

    return {
        "goal": req.goal,
        "subtasks": subtask_list,
        "aggregated_output": aggregate_result.get("aggregated_output", ""),
        "execution_trace": trace,
        "enabled_capabilities": enabled_caps,
    }
