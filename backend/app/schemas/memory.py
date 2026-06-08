"""Pydantic schemas for user memory management"""
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class MemoryOut(BaseModel):
    """Single memory item returned by API"""
    id: uuid.UUID
    category: str
    key: str
    content: str
    confidence: float
    is_active: bool
    source_conversation_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    """List of memories for a user"""
    memories: list[MemoryOut]
    total: int


class MemoryDeleteAllRequest(BaseModel):
    """Request to delete all memories — requires explicit confirmation"""
    confirm: bool = Field(
        False,
        description="Must be true to confirm deletion of all memories"
    )


class MemoryDeleteResponse(BaseModel):
    """Response after deleting a memory or all memories"""
    ok: bool
    deleted: str  # "1 memory" or "all 5 memories"
