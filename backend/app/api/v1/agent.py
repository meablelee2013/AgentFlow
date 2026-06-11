"""Agent API — tool-calling agent endpoints with user memory"""
from fastapi import APIRouter, Depends, Header, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import uuid

from app.core.engine.agent_engine import AgentGraphEngine
from app.core.engine.prompts import AGENT_SYSTEM_PROMPT, get_prompt_builder, PromptContext
from app.core.engine.loop_guard import LoopGuard
from app.core.memory.extractor import MemoryExtractor
from app.core.metrics import get_llm_stats
from app.core.tool.registry import ToolRegistry
from app.api.v1.deps import get_db, AsyncSessionLocal
from app.services.chat_service import ChatService

logger = structlog.get_logger()
router = APIRouter(prefix="/agent", tags=["agent"])

_agent_engine: AgentGraphEngine | None = None

def _get_agent_engine() -> AgentGraphEngine:
    """Lazy-init: ensures engine picks up PG checkpointer after startup."""
    global _agent_engine
    if _agent_engine is None:
        _agent_engine = AgentGraphEngine()
    return _agent_engine
extractor = MemoryExtractor()


class AgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None


class AgentResponse(BaseModel):
    thread_id: str
    message: str
    is_new: bool


class ToolInfo(BaseModel):
    name: str
    description: str


def _parse_memory_enabled(
    x_memory_enabled: str | None = Header("true", alias="X-Memory-Enabled"),
) -> bool:
    return x_memory_enabled.lower() not in ("false", "0", "no", "off")


def _parse_user_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> uuid.UUID | None:
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


async def _extract_memories_bg(
    thread_id: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    reply: str,
    memory_enabled: bool = True,
):
    from app.config import settings

    if not memory_enabled:
        logger.debug("memory_extraction_disabled_by_user", thread_id=thread_id)
        return

    async with AsyncSessionLocal() as db:
        try:
            service = ChatService(db)
            recent = await service.get_recent_messages(
                thread_id, limit=settings.MEMORY_EXTRACTION_MAX_MESSAGES,
            )
            if not recent:
                recent = [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": reply},
                ]
            await extractor.extract_and_persist(
                thread_id=thread_id,
                conversation_id=conversation_id,
                user_id=user_id,
                messages=recent,
                db_session=db,
            )
        except Exception:
            logger.exception("bg_agent_memory_extraction_failed", thread_id=thread_id)


@router.post("", response_model=AgentResponse)
async def agent_chat(
    req: AgentRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    user_id: uuid.UUID | None = Depends(_parse_user_id),
    memory_enabled: bool = Depends(_parse_memory_enabled),
):
    """Send message to agent with tool access — synchronous."""
    builder = get_prompt_builder()
    ctx = PromptContext(
        user_id=str(user_id) if user_id else None,
        memory_enabled=memory_enabled,
        db=db,
    )
    sp = await builder.build(ctx)
    if not sp.strip():
        sp = AGENT_SYSTEM_PROMPT  # fallback

    result = await _get_agent_engine().run(
        [{"role": "user", "content": req.message}],
        thread_id=req.thread_id,
        system_prompt=sp,
    )
    reply = result["messages"][-1]["content"] if result["messages"] else ""
    tid = result["thread_id"]

    service = ChatService(db)
    conv = await service.save_message(tid, "user", req.message, user_id=user_id)
    await service.save_message(tid, "assistant", reply, user_id=user_id)

    if user_id and background_tasks and memory_enabled:
        background_tasks.add_task(
            _extract_memories_bg, tid, conv.id, user_id, req.message, reply, memory_enabled,
        )

    return AgentResponse(thread_id=tid, message=reply, is_new=result["is_new"])


@router.post("/stream")
async def agent_stream(
    req: AgentRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    user_id: uuid.UUID | None = Depends(_parse_user_id),
    memory_enabled: bool = Depends(_parse_memory_enabled),
):
    """Send message to agent — SSE streaming."""
    async def event_stream():
        tid = req.thread_id or str(uuid.uuid4())
        full_response = ""
        yield f"data: [THREAD:{tid}]\n\n"

        builder = get_prompt_builder()
        ctx = PromptContext(
            user_id=str(user_id) if user_id else None,
            memory_enabled=memory_enabled,
            db=db,
        )
        sp = await builder.build(ctx)
        if not sp.strip():
            sp = AGENT_SYSTEM_PROMPT

        async for token in _get_agent_engine().stream(
            [{"role": "user", "content": req.message}],
            thread_id=tid,
            system_prompt=sp,
        ):
            full_response += token
            yield f"data: {token}\n\n"
        yield f"data: [DONE]\n\n"

        service = ChatService(db)
        conv = await service.save_message(tid, "user", req.message, user_id=user_id)
        await service.save_message(tid, "assistant", full_response, user_id=user_id)

        if user_id and background_tasks and memory_enabled:
            background_tasks.add_task(
                _extract_memories_bg, tid, conv.id, user_id, req.message, full_response, memory_enabled,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all available agent tools."""
    return [
        ToolInfo(name=t.name, description=t.description)
        for t in _get_agent_engine().tools
    ]


@router.post("/{thread_id}/cancel")
async def cancel_execution(thread_id: str):
    """Cancel a running agent execution (Layer 4 — user interrupt).

    Sets a cancel flag that the LoopGuard checks before each tool
    execution. The agent will finish its current LLM call and then
    stop gracefully.
    """
    engine = _get_agent_engine()
    was_new = engine.cancel(thread_id)
    return {
        "thread_id": thread_id,
        "cancelled": True,
        "was_new": was_new,
    }


@router.get("/{thread_id}/guard")
async def get_guard_summary(thread_id: str):
    """Get the LoopGuard safety summary for a thread.

    Returns token ratio, iteration count, confidence scores, etc.
    Useful for debugging why an agent stopped.
    """
    engine = _get_agent_engine()
    summary = engine.get_guard_summary(thread_id)
    if not summary:
        return {"thread_id": thread_id, "status": "not_found"}
    return {"thread_id": thread_id, **summary}


@router.get("/stats/llm")
async def get_llm_stats_endpoint():
    """Get real-time LLM call statistics (QPS, P50/P90/P99 latency).

    Returns the same data exposed via Prometheus /metrics, but as JSON.
    """
    return get_llm_stats()
