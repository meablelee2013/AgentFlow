"""
Checkpointer 管理器

管理 LangGraph 的检查点后端，支持热切换 MemorySaver ↔ SqliteSaver。

Checkpointer 继承链:
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

    note for MemorySaver "= InMemorySaver (alias)\nlanggraph 内置"
    note for SqliteSaver "pip install langgraph-checkpoint-sqlite"
    note for PostgresSaver "pip install langgraph-checkpoint-postgres"
```

存储结构 (MemorySaver):
    三层嵌套 defaultdict
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
    """Checkpointer 管理器

    Phase 1: 使用 MemorySaver（开发）
    Phase 2: 切换到 SqliteSaver（生产准备）
    Phase 3: 切换到 PostgresSaver（集群部署）

    用法:
        manager = CheckpointerManager()
        checkpointer = manager.get()
        app = graph.compile(checkpointer=checkpointer)
    """

    _instance: MemorySaver | None = None

    @classmethod
    def get(cls) -> MemorySaver:
        """获取 Checkpointer 实例（单例）

        Returns:
            MemorySaver 实例
        """
        if cls._instance is None:
            cls._instance = MemorySaver()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置 Checkpointer（测试用）"""
        cls._instance = None
