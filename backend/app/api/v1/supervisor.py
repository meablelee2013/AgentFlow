"""Supervisor Multi-Agent API — orchestrated specialist team"""
import uuid
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.engine.supervisor_engine import SupervisorEngine
from app.api.v1.deps import get_db
from app.services.chat_service import ChatService

logger = structlog.get_logger()
router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

engine = SupervisorEngine()


class MultiAgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    thread_id: str | None = None


class MultiAgentResponse(BaseModel):
    thread_id: str
    message: str
    is_new: bool


@router.post("", response_model=MultiAgentResponse)
async def multi_agent_chat(req: MultiAgentRequest, db: AsyncSession = Depends(get_db)):
    """Send task to supervisor multi-agent team — synchronous."""
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
    await service.save_message(tid, "user", req.message)
    await service.save_message(tid, "assistant", reply)

    return MultiAgentResponse(thread_id=tid, message=reply, is_new=result["is_new"])


@router.post("/stream")
async def multi_agent_stream(req: MultiAgentRequest, db: AsyncSession = Depends(get_db)):
    """Send task — SSE streaming with supervisor routing visibility."""
    async def event_stream():
        tid = req.thread_id or str(uuid.uuid4())
        full_response = ""
        yield f"data: [THREAD:{tid}]\n\n"

        async for token in engine.stream(
            [{"role": "user", "content": req.message}],
            thread_id=tid,
        ):
            full_response += token
            yield f"data: {token}\n\n"
        yield f"data: [DONE]\n\n"

        service = ChatService(db)
        await service.save_message(tid, "user", req.message)
        await service.save_message(tid, "assistant", full_response)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
