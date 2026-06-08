"""MemoryService — CRUD + dedup + prompt formatting for user memories"""
import uuid
from typing import Sequence

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory

# Categories for factory function
MEMORY_CATEGORIES = ["personal", "preference", "project", "relationship", "context"]

# Max memories to inject into system prompt (to control token usage)
MAX_MEMORIES_IN_PROMPT = 20


class MemoryService:
    """Manages user_memories table.

    Dedup strategy for upsert_memory:
        1. Find existing active memory with same (user_id, key)
        2. Same content (or trivially rephrased) → skip (no-op)
        3. Refined content (longer, more specific) → update in place
        4. Contradictory content → deactivate old, insert new
        5. No existing match → insert new
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_memory(
        self,
        user_id: uuid.UUID,
        category: str,
        key: str,
        content: str,
        confidence: float = 1.0,
        source_conversation_id: uuid.UUID | None = None,
    ) -> UserMemory | None:
        """Upsert a memory fact — deduplicate by (user_id, key).

        Returns the UserMemory if created/updated, None if skipped (duplicate).
        """
        # Normalize key for matching
        normalized_key = key.strip().lower()
        normalized_content = content.strip()

        # Find existing active memory with same user_id and key
        result = await self.db.execute(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.key.ilike(normalized_key),
                UserMemory.is_active.is_(True),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Compare content — skip if essentially same
            existing_normalized = (existing.content or "").strip()
            if self._is_same_content(existing_normalized, normalized_content):
                return None  # No-op, duplicate

            if self._is_contradiction(existing_normalized, normalized_content):
                # Deactivate old, insert new below
                existing.is_active = False
                await self.db.flush()
            else:
                # Refinement — update in place
                existing.content = normalized_content
                existing.confidence = confidence
                if source_conversation_id:
                    existing.source_conversation_id = source_conversation_id
                await self.db.commit()
                return existing

        # Insert new memory
        memory = UserMemory(
            user_id=user_id,
            category=category,
            key=normalized_key,
            content=normalized_content,
            confidence=confidence,
            source_conversation_id=source_conversation_id,
        )
        self.db.add(memory)
        await self.db.commit()
        await self.db.refresh(memory)
        return memory

    async def get_all_active(self, user_id: uuid.UUID) -> Sequence[UserMemory]:
        """Return all active memories for a user, ordered by category then created_at."""
        result = await self.db.execute(
            select(UserMemory)
            .where(
                UserMemory.user_id == user_id,
                UserMemory.is_active.is_(True),
            )
            .order_by(UserMemory.category, UserMemory.created_at)
        )
        return result.scalars().all()

    async def get_active_by_category(
        self, user_id: uuid.UUID, category: str
    ) -> Sequence[UserMemory]:
        """Return active memories for a user in a given category."""
        result = await self.db.execute(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.category == category,
                UserMemory.is_active.is_(True),
            )
        )
        return result.scalars().all()

    async def deactivate_memory(
        self, memory_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Soft delete — set is_active=False. Returns True if a row was updated."""
        result = await self.db.execute(
            update(UserMemory)
            .where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
            )
            .values(is_active=False)
        )
        await self.db.commit()
        return result.rowcount > 0

    async def hard_delete_memory(
        self, memory_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        """Hard delete a memory. Returns True if a row was deleted."""
        result = await self.db.execute(
            delete(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.user_id == user_id,
            )
        )
        await self.db.commit()
        return result.rowcount > 0

    async def delete_all_for_user(self, user_id: uuid.UUID) -> int:
        """Hard delete all memories for a user. Returns count of deleted rows."""
        result = await self.db.execute(
            delete(UserMemory).where(UserMemory.user_id == user_id)
        )
        await self.db.commit()
        return result.rowcount

    async def format_for_system_prompt(self, user_id: uuid.UUID) -> str:
        """Format all active memories as a string for system prompt injection.

        Returns empty string if no memories exist.

        Output format:
            ## User Memory (remembered from past conversations)
            - [personal] User's name is Alice
            - [preference] User prefers TypeScript for new projects
        """
        memories = await self.get_all_active(user_id)
        if not memories:
            return ""

        lines = ["## User Memory (remembered from past conversations)"]
        for m in memories[:MAX_MEMORIES_IN_PROMPT]:
            lines.append(f"- [{m.category}] {m.content}")

        return "\n".join(lines)

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _is_same_content(existing: str, new: str) -> bool:
        """Check if two content strings are essentially identical."""
        a = existing.strip().lower().rstrip(".")
        b = new.strip().lower().rstrip(".")
        if a == b:
            return True
        # One is a substring of the other (refinement case)
        if len(a) > len(b):
            a, b = b, a
        # If the shorter is fully contained in the longer, it's a refinement,
        # not a duplicate — return False to trigger update
        return False

    @staticmethod
    def _is_contradiction(existing: str, new: str) -> bool:
        """Simple heuristic: if key phrases are negated or substantially different.

        This is a basic check — the LLM extraction handles most dedup by using
        consistent keys. Explicit contradictions are rare.
        """
        a_words = set(existing.lower().split())
        b_words = set(new.lower().split())

        # Very different word sets may indicate contradiction
        overlap = a_words & b_words
        total = a_words | b_words
        if not total:
            return False
        jaccard = len(overlap) / len(total)
        # Low overlap = possibly contradictory
        return jaccard < 0.15
