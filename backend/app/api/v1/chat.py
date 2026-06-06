"""Chat API — conversation endpoints"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import structlog

from app.core.engine.chat_engine import ChatGraphEngine

logger = structlog.get_logger()
router = APIRouter(prefix="/chat", tags=["chat"])

# Global engine instance (use dependency injection in production)
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


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send message — synchronous full response"""
    result = await engine.run(
        [{"role": "user", "content": req.message}],
        thread_id=req.thread_id,
    )
    reply = result["messages"][-1]["content"] if result["messages"] else ""
    return ChatResponse(
        thread_id=result["thread_id"],
        message=reply,
        is_new=result["is_new"],
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Send message — SSE streaming response"""
    async def event_stream():
        async for token in engine.stream(
            [{"role": "user", "content": req.message}],
            thread_id=req.thread_id,
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/history/{thread_id}", response_model=HistoryResponse)
async def get_history(thread_id: str):
    """Get conversation history messages"""
    messages = await engine.get_history(thread_id)
    return HistoryResponse(thread_id=thread_id, messages=messages)
