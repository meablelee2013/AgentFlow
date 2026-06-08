"""Supervisor Multi-Agent API — orchestrated specialist team with user memory"""
import uuid
from fastapi import APIRouter, Depends, Header, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.engine.supervisor_engine import SupervisorEngine
from app.core.engine.prompts import (
    SUPERVISOR_SYSTEM_PROMPT,
    AGENT_PROMPTS,
)
from app.core.memory import build_system_prompt
from app.core.memory.extractor import MemoryExtractor
from app.api.v1.deps import get_db, AsyncSessionLocal
from app.services.chat_service import ChatService

logger = structlog.get_logger()
router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

extractor = MemoryExtractor()


class MultiAgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None


class MultiAgentResponse(BaseModel):
    thread_id: str
    message: str
    is_new: bool


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
):
    from app.config import settings

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
            logger.exception("bg_supervisor_memory_extraction_failed", thread_id=thread_id)


@router.post("", response_model=MultiAgentResponse)
async def multi_agent_chat(
    req: MultiAgentRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    user_id: uuid.UUID | None = Depends(_parse_user_id),
):
    """Send task to supervisor multi-agent team — synchronous."""
    # Build supervisor prompt with user memories
    sp = SUPERVISOR_SYSTEM_PROMPT
    if user_id:
        sp = await build_system_prompt(
            base_prompt=SUPERVISOR_SYSTEM_PROMPT,
            user_id=user_id,
            db=db,
        )

    engine = SupervisorEngine(
        supervisor_prompt=sp,
        agent_prompts=AGENT_PROMPTS,  # agent prompts unchanged
    )

    result = await engine.run(
        [{"role": "user", "content": req.message}],
        thread_id=req.thread_id,
    )
    messages = result["messages"]
    # Get only the last assistant message (final answer from reviewer or last agent)
    reply = ""
    for m in reversed(messages):
        if m["role"] == "assistant":
            reply = m["content"]
            break

    tid = result["thread_id"]
    service = ChatService(db)
    conv = await service.save_message(tid, "user", req.message, user_id=user_id)
    await service.save_message(tid, "assistant", reply, user_id=user_id)

    if user_id and background_tasks:
        background_tasks.add_task(
            _extract_memories_bg, tid, conv.id, user_id, req.message, reply,
        )

    return MultiAgentResponse(thread_id=tid, message=reply, is_new=result["is_new"])


@router.post("/stream")
async def multi_agent_stream(
    req: MultiAgentRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    user_id: uuid.UUID | None = Depends(_parse_user_id),
):
    """Send task — SSE streaming with supervisor routing visibility."""
    async def event_stream():
        tid = req.thread_id or str(uuid.uuid4())
        full_response = ""
        yield f"data: [THREAD:{tid}]\n\n"

        # Build supervisor prompt with user memories
        sp = SUPERVISOR_SYSTEM_PROMPT
        if user_id:
            sp = await build_system_prompt(
                base_prompt=SUPERVISOR_SYSTEM_PROMPT,
                user_id=user_id,
                db=db,
            )

        engine = SupervisorEngine(
            supervisor_prompt=sp,
            agent_prompts=AGENT_PROMPTS,
        )

        async for token in engine.stream(
            [{"role": "user", "content": req.message}],
            thread_id=tid,
        ):
            full_response += token
            yield f"data: {token}\n\n"
        yield f"data: [DONE]\n\n"

        service = ChatService(db)
        conv = await service.save_message(tid, "user", req.message, user_id=user_id)
        await service.save_message(tid, "assistant", full_response, user_id=user_id)

        if user_id and background_tasks:
            background_tasks.add_task(
                _extract_memories_bg, tid, conv.id, user_id, req.message, full_response,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")
