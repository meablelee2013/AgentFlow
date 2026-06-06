"""ORM 模型注册 — 导入所有模型以被 Alembic 发现"""
from app.models.base import Base
from app.models.user import User, Workspace, WorkspaceMember, UserRole
from app.models.conversation import Conversation, Message
from app.models.knowledge import KnowledgeBase, Document, DocumentChunk

__all__ = [
    "Base",
    "User",
    "Workspace",
    "WorkspaceMember",
    "UserRole",
    "Conversation",
    "Message",
    "KnowledgeBase",
    "Document",
    "DocumentChunk",
]
