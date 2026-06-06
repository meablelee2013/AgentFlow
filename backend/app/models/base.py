"""SQLAlchemy 声明式基类 — 所有 ORM 模型继承此类"""
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncAttrs


class Base(AsyncAttrs, DeclarativeBase):
    pass
