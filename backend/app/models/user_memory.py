"""UserMemory model — cross-conversation user facts"""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Float, Text, Boolean, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class UserMemory(Base):
    """Cross-conversation user fact — extracted asynchronously after each turn.

    Scoped by user_id (client-side UUID until auth is implemented).
    When auth arrives, user_id can be backfilled to FK -> users.id.

    Dedup strategy (in MemoryService):
        Same (user_id, key) + same content   → skip (no-op)
        Same (user_id, key) + refined content → update in place
        Same (user_id, key) + contradictory   → deactivate old, insert new
    """

    __tablename__ = "user_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False,
        comment="User identifier — client-side UUID (future: FK → users.id)"
    )
    category: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False,
        comment="Fact category: personal | preference | project | relationship | context"
    )
    key: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Short label, e.g. 'User's name', 'Preferred language'"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Full fact sentence, e.g. 'User's name is Alice, a backend engineer'"
    )
    confidence: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False,
        comment="Extraction confidence 0.0–1.0"
    )
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        index=True, nullable=True,
        comment="Conversation that produced this memory"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False,
        comment="Soft delete — inactive memories are not injected into prompts"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
