"""ORM model registry — import all models so Alembic can discover them"""
from app.models.base import Base
from app.models.conversation import Conversation, Message
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk

__all__ = [
    "Base",
    "Conversation",
    "Message",
    "KnowledgeBase",
    "Document",
    "DocumentChunk",
]
