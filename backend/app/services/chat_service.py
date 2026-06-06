"""Chat service — persists conversations and messages to PostgreSQL"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.conversation import Conversation, Message


class ChatService:
    """Service layer for conversation persistence"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> Conversation:
        """Save a message, creating the conversation if it doesn't exist.

        Args:
            thread_id: LangGraph thread identifier
            role: 'user' or 'assistant'
            content: message text
            workspace_id: optional workspace to associate

        Returns:
            The Conversation (existing or newly created)
        """
        # Find or create conversation
        result = await self.db.execute(
            select(Conversation).where(Conversation.thread_id == thread_id)
        )
        conv = result.scalar_one_or_none()

        if conv is None:
            conv = Conversation(
                thread_id=thread_id,
                title=content[:80] if role == "user" else "New Conversation",
                workspace_id=workspace_id,
            )
            self.db.add(conv)
            await self.db.flush()

        # Save the message
        message = Message(
            conversation_id=conv.id,
            role=role,
            content=content,
        )
        self.db.add(message)
        await self.db.commit()

        return conv

    async def get_history(self, thread_id: str) -> list[dict]:
        """Get all messages for a thread, ordered by creation time.

        Args:
            thread_id: LangGraph thread identifier

        Returns:
            List of {role, content} dicts
        """
        result = await self.db.execute(
            select(Conversation).where(Conversation.thread_id == thread_id)
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            return []

        # Reload with messages
        await self.db.refresh(conv, attribute_names=["messages"])
        return [
            {"role": m.role, "content": m.content}
            for m in sorted(conv.messages, key=lambda m: m.created_at)
        ]
