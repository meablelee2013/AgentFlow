"""Chat API — conversation endpoints with PostgreSQL persistence and user memory"""
import uuid
from fastapi import APIRouter, Depends, Header, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from app.core.engine.chat_engine import ChatGraphEngine
from app.core.engine.prompts import (
    CHAT_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT_STREAM,
    get_prompt_builder, PromptContext,
)
from app.core.memory.extractor import MemoryExtractor
from app.api.v1.deps import get_db, AsyncSessionLocal
from app.services.chat_service import ChatService
from app.models.conversation import Conversation as ConvModel

logger = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])

_chat_engine: ChatGraphEngine | None = None

def _get_chat_engine() -> ChatGraphEngine:
    global _chat_engine
    if _chat_engine is None:
        _chat_engine = ChatGraphEngine()
    return _chat_engine
extractor = MemoryExtractor()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User message")
    thread_id: str | None = Field(None, description="Session ID, new if omitted")


class ChatResponse(BaseModel):
    thread_id: str
    message: str
    is_new: bool


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[dict]


class ConversationItem(BaseModel):
    thread_id: str
    title: str
    updated_at: str | None = None


def _parse_user_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> uuid.UUID | None:
    """Parse X-User-Id header to UUID."""
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        return None


def _parse_memory_enabled(
    x_memory_enabled: str | None = Header("true", alias="X-Memory-Enabled"),
) -> bool:
    """Parse X-Memory-Enabled header. Defaults to true (opt-out)."""
    return x_memory_enabled.lower() not in ("false", "0", "no", "off")


async def _extract_memories_background(
    thread_id: str,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    message: str,
    reply: str,
    memory_enabled: bool = True,
):
    """Background task: extract user memories after response completes."""
    from app.config import settings

    if not memory_enabled:
        logger.debug("memory_extraction_disabled_by_user", thread_id=thread_id)
        return

    async with AsyncSessionLocal() as db:
        try:
            service = ChatService(db)
            recent = await service.get_recent_messages(
                thread_id,
                limit=settings.MEMORY_EXTRACTION_MAX_MESSAGES,
            )
            # If recent is empty (first message), use the just-sent exchange
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
            logger.exception(
                "background_memory_extraction_failed",
                thread_id=thread_id,
            )


@router.get("/conversations", response_model=list[ConversationItem])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(_parse_user_id),
):
    """List conversation threads for the current user."""
    stmt = select(ConvModel).order_by(ConvModel.updated_at.desc()).limit(50)
    if user_id:
        stmt = stmt.where(ConvModel.user_id == user_id)
    result = await db.execute(stmt)
    convs = result.scalars().all()
    return [
        ConversationItem(
            thread_id=c.thread_id,
            title=c.title or "Untitled",
            updated_at=c.updated_at.isoformat() if c.updated_at else None,
        )
        for c in convs
    ]


@router.post("", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    user_id: uuid.UUID | None = Depends(_parse_user_id),
    memory_enabled: bool = Depends(_parse_memory_enabled),
):
    """Send message — synchronous full response"""
    builder = get_prompt_builder()
    ctx = PromptContext(
        user_id=str(user_id) if user_id else None,
        memory_enabled=memory_enabled,
        db=db,
    )
    sp = await builder.build(ctx)
    if not sp.strip():
        sp = CHAT_SYSTEM_PROMPT  # fallback

    result = await _get_chat_engine().run(
        [{"role": "user", "content": req.message}],
        thread_id=req.thread_id,
        system_prompt=sp,
    )
    reply = result["messages"][-1]["content"] if result["messages"] else ""
    tid = result["thread_id"]

    # Persist both user message and assistant response to PostgreSQL
    service = ChatService(db)
    conv = await service.save_message(tid, "user", req.message, user_id=user_id)
    await service.save_message(tid, "assistant", reply, user_id=user_id)

    # Schedule background memory extraction
    if user_id and background_tasks and memory_enabled:
        background_tasks.add_task(
            _extract_memories_background,
            tid, conv.id, user_id, req.message, reply, memory_enabled,
        )

    return ChatResponse(
        thread_id=tid,
        message=reply,
        is_new=result["is_new"],
    )


@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    user_id: uuid.UUID | None = Depends(_parse_user_id),
    memory_enabled: bool = Depends(_parse_memory_enabled),
):
    """Send message — SSE streaming response, persisted to PostgreSQL"""
    async def event_stream():
        tid = req.thread_id or str(uuid.uuid4())
        full_response = ""  # Accumulate for DB persistence
        # Send thread_id as first event
        yield f"data: [THREAD:{tid}]\n\n"

        builder = get_prompt_builder()
        ctx = PromptContext(
            user_id=str(user_id) if user_id else None,
            memory_enabled=memory_enabled,
            db=db,
        )
        sp = await builder.build(ctx)
        if not sp.strip():
            sp = CHAT_SYSTEM_PROMPT_STREAM

        async for token in _get_chat_engine().stream(
            [{"role": "user", "content": req.message}],
            thread_id=tid,
            system_prompt=sp,
        ):
            full_response += token
            yield f"data: {token}\n\n"
        yield f"data: [DONE]\n\n"

        # Persist after streaming completes
        service = ChatService(db)
        conv = await service.save_message(tid, "user", req.message, user_id=user_id)
        await service.save_message(tid, "assistant", full_response, user_id=user_id)

        # Schedule background memory extraction
        if user_id and background_tasks and memory_enabled:
            background_tasks.add_task(
                _extract_memories_background,
                tid, conv.id, user_id, req.message, full_response, memory_enabled,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history/{thread_id}", response_model=HistoryResponse)
async def get_history(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Get conversation history messages — from PostgreSQL"""
    service = ChatService(db)
    messages = await service.get_history(thread_id)

    # Fallback to LangGraph MemorySaver if DB has no records yet
    if not messages:
        messages = await _get_chat_engine().get_history(thread_id)

    return HistoryResponse(thread_id=thread_id, messages=messages)
