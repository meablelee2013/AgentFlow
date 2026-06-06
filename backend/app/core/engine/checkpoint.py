"""
Checkpointer manager

Manages LangGraph checkpoint backends, supports hot-swap MemorySaver ↔ SqliteSaver.

Checkpointer inheritance chain:
```mermaid
classDiagram
    class BaseCheckpointSaver~V~ {
        <<abstract>>
        +serde: SerializerProtocol
        +get_tuple(config) CheckpointTuple
        +list(config, filter, before, limit) Iterator
        +put(config, checkpoint, metadata, new_versions) RunnableConfig
        +put_writes(config, writes, task_id) None
        +delete_thread(thread_id) None
        +get_next_version(current, channel) V
    }
    class MemorySaver {
        +storage: defaultdict
        +writes: defaultdict
        +blobs: dict
    }
    class SqliteSaver {
        +conn: sqlite3.Connection
        +setup() None
    }
    class PostgresSaver {
        +pool: AsyncConnectionPool
    }
    BaseCheckpointSaver <|-- MemorySaver
    BaseCheckpointSaver <|-- SqliteSaver
    BaseCheckpointSaver <|-- PostgresSaver

    note for MemorySaver "= InMemorySaver (alias)\nlanggraph built-in"
    note for SqliteSaver "pip install langgraph-checkpoint-sqlite"
    note for PostgresSaver "pip install langgraph-checkpoint-postgres"
```

Storage structure (MemorySaver):
    Triple-nested defaultdict
    storage[thread_id][checkpoint_ns][checkpoint_id] = (
        serialized_checkpoint,    # (type, bytes)
        serialized_metadata,      # (type, bytes)
        parent_checkpoint_id,     # str | None
    )
    writes[(thread_id, checkpoint_ns, checkpoint_id)] = {
        (task_id, write_idx): (task_id, channel, serialized_value, task_path)
    }
    blobs[(thread_id, checkpoint_ns, channel, version)] = (
        format, bytes
    )
"""

from langgraph.checkpoint.memory import MemorySaver


class CheckpointerManager:
    """Checkpointer manager

    Phase 1: use MemorySaver (development)
    Phase 2: switch to SqliteSaver (production-ready)
    Phase 3: switch to PostgresSaver (cluster deployment)

    Usage:
        manager = CheckpointerManager()
        checkpointer = manager.get()
        app = graph.compile(checkpointer=checkpointer)
    """

    _instance: MemorySaver | None = None

    @classmethod
    def get(cls) -> MemorySaver:
        """Get Checkpointer instance (singleton)

        Returns:
            MemorySaver instance
        """
        if cls._instance is None:
            cls._instance = MemorySaver()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset Checkpointer (for testing)"""
        cls._instance = None
