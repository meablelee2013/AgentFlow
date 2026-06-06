"""Agent API — tool-calling agent endpoints"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import uuid

from app.core.engine.agent_engine import AgentGraphEngine
from app.core.tool.registry import ToolRegistry
from app.api.v1.deps import get_db
from app.services.chat_service import ChatService

logger = structlog.get_logger()
router = APIRouter(prefix="/agent", tags=["agent"])

agent_engine = AgentGraphEngine()


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


@router.post("", response_model=AgentResponse)
async def agent_chat(req: AgentRequest, db: AsyncSession = Depends(get_db)):
    """Send message to agent with tool access — synchronous."""
    result = await agent_engine.run(
        [{"role": "user", "content": req.message}],
        thread_id=req.thread_id,
    )
    reply = result["messages"][-1]["content"] if result["messages"] else ""
    tid = result["thread_id"]

    service = ChatService(db)
    await service.save_message(tid, "user", req.message)
    await service.save_message(tid, "assistant", reply)

    return AgentResponse(thread_id=tid, message=reply, is_new=result["is_new"])


@router.post("/stream")
async def agent_stream(req: AgentRequest, db: AsyncSession = Depends(get_db)):
    """Send message to agent — SSE streaming."""
    async def event_stream():
        tid = req.thread_id or str(uuid.uuid4())
        full_response = ""
        yield f"data: [THREAD:{tid}]\n\n"

        async for token in agent_engine.stream(
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


@router.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all available agent tools."""
    return [
        ToolInfo(name=t.name, description=t.description)
        for t in agent_engine.tools
    ]
