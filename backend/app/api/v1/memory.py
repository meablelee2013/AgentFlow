"""Memory API — manage user memories"""
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.v1.deps import get_db
from app.services.memory_service import MemoryService
from app.schemas.memory import (
    MemoryOut,
    MemoryListResponse,
    MemoryDeleteAllRequest,
    MemoryDeleteResponse,
)

logger = structlog.get_logger()
router = APIRouter(prefix="/memory", tags=["memory"])


def _get_user_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> uuid.UUID | None:
    """Extract user_id from X-User-Id header."""
    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-User-Id header")


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(_get_user_id),
):
    """List all active memories for the current user."""
    if user_id is None:
        return MemoryListResponse(memories=[], total=0)

    service = MemoryService(db)
    memories = await service.get_all_active(user_id)

    return MemoryListResponse(
        memories=[MemoryOut.model_validate(m) for m in memories],
        total=len(memories),
    )


@router.delete("/{memory_id}", response_model=MemoryDeleteResponse)
async def delete_memory(
    memory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(_get_user_id),
):
    """Soft-delete a single memory."""
    if user_id is None:
        raise HTTPException(status_code=401, detail="X-User-Id header required")

    service = MemoryService(db)
    ok = await service.deactivate_memory(memory_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found or not owned by user")

    logger.info("memory_deleted", memory_id=str(memory_id), user_id=str(user_id))
    return MemoryDeleteResponse(ok=True, deleted="1 memory")


@router.delete("", response_model=MemoryDeleteResponse)
async def delete_all_memories(
    req: MemoryDeleteAllRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID | None = Depends(_get_user_id),
):
    """Clear all memories for the current user. Requires confirmation."""
    if user_id is None:
        raise HTTPException(status_code=401, detail="X-User-Id header required")

    if not req.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to delete all memories")

    service = MemoryService(db)
    count = await service.delete_all_for_user(user_id)

    logger.info("all_memories_deleted", user_id=str(user_id), count=count)
    return MemoryDeleteResponse(ok=True, deleted=f"all {count} memories")
