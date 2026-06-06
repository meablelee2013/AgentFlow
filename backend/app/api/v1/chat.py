"""Chat API — conversation endpoints with PostgreSQL persistence"""
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.engine.chat_engine import ChatGraphEngine
from app.api.v1.deps import get_db
from app.services.chat_service import ChatService

logger = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])

engine = ChatGraphEngine()


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


@router.get("/conversations", response_model=list[ConversationItem])
async def list_conversations(db: AsyncSession = Depends(get_db)):
    """List all conversation threads."""
    from sqlalchemy import select
    from app.models.conversation import Conversation as ConvModel
    result = await db.execute(
        select(ConvModel).order_by(ConvModel.updated_at.desc()).limit(50)
    )
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
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    """Send message — synchronous full response"""
    result = await engine.run(
        [{"role": "user", "content": req.message}],
        thread_id=req.thread_id,
    )
    reply = result["messages"][-1]["content"] if result["messages"] else ""
    tid = result["thread_id"]

    # Persist both user message and assistant response to PostgreSQL
    service = ChatService(db)
    await service.save_message(tid, "user", req.message)
    await service.save_message(tid, "assistant", reply)

    return ChatResponse(
        thread_id=tid,
        message=reply,
        is_new=result["is_new"],
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Send message — SSE streaming response with thread_id"""
    async def event_stream():
        tid = req.thread_id or str(uuid.uuid4())
        # Send thread_id as first event
        yield f"data: [THREAD:{tid}]\n\n"

        async for token in engine.stream(
            [{"role": "user", "content": req.message}],
            thread_id=tid,
        ):
            yield f"data: {token}\n\n"
        yield f"data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history/{thread_id}", response_model=HistoryResponse)
async def get_history(thread_id: str, db: AsyncSession = Depends(get_db)):
    """Get conversation history messages — from PostgreSQL"""
    service = ChatService(db)
    messages = await service.get_history(thread_id)

    # Fallback to LangGraph MemorySaver if DB has no records yet
    if not messages:
        messages = await engine.get_history(thread_id)

    return HistoryResponse(thread_id=thread_id, messages=messages)
