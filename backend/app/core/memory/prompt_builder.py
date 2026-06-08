"""System prompt builder — inject user memories into base prompts"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.memory_service import MemoryService


async def build_system_prompt(
    base_prompt: str,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> str:
    """Prepend user memories to the base system prompt.

    Args:
        base_prompt: The engine's default system prompt
        user_id: User identifier for memory scoping
        db: Async database session

    Returns:
        Combined system prompt with memories (if any exist)
    """
    if user_id is None:
        return base_prompt

    memory_service = MemoryService(db)
    memories_text = await memory_service.format_for_system_prompt(user_id)

    if memories_text:
        return f"{base_prompt}\n\n{memories_text}"

    return base_prompt
