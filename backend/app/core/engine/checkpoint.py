"""Checkpointer — PG-backed with ConnectionPool. Monkey-patches async methods
so PostgresSaver works with ainvoke() by delegating to sync methods via to_thread."""
import asyncio
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from app.config import settings


def _patch_async(saver):
    """PostgresSaver is sync-only. Patch async methods → delegate to sync via thread."""
    async def _aget_tuple(self, config):
        return await asyncio.to_thread(self.get_tuple, config)
    async def _aput(self, config, checkpoint, metadata, new_versions):
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)
    async def _aput_writes(self, config, writes, task_id):
        return await asyncio.to_thread(self.put_writes, config, writes, task_id)
    async def _adelete_thread(self, thread_id):
        return await asyncio.to_thread(self.delete_thread, thread_id)
    # Bind to instance
    saver.aget_tuple = _aget_tuple.__get__(saver, type(saver))
    saver.aput = _aput.__get__(saver, type(saver))
    saver.aput_writes = _aput_writes.__get__(saver, type(saver))
    saver.adelete_thread = _adelete_thread.__get__(saver, type(saver))
    return saver


class CheckpointerManager:
    _instance = None
    _pool = None

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = MemorySaver()
        return cls._instance

    @classmethod
    def init_postgres(cls):
        conn_string = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        cls._pool = ConnectionPool(conninfo=conn_string, min_size=2, max_size=10)
        saver = PostgresSaver(cls._pool)
        saver.setup()
        cls._instance = _patch_async(saver)

    @classmethod
    def shutdown(cls):
        if cls._pool:
            cls._pool.close()
            cls._pool = None
            cls._instance = MemorySaver()