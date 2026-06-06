"""FastAPI dependencies — database sessions and common utilities"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Yield an async database session — FastAPI dependency injection."""
    async with AsyncSessionLocal() as session:
        yield session
