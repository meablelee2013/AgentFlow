"""ORM model registry — import all models so Alembic can discover them"""
from app.models.base import Base
from app.models.user import User, Workspace, WorkspaceMember, UserRole
from app.models.conversation import Conversation, Message
from app.models.user_memory import UserMemory
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk

__all__ = [
    "Base",
    "User",
    "Workspace",
    "WorkspaceMember",
    "UserRole",
    "Conversation",
    "Message",
    "UserMemory",
    "KnowledgeBase",
    "Document",
    "DocumentChunk",
]
