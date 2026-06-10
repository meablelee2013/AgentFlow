"""Database node executor — query PostgreSQL / MySQL.

Phase 4 will add full implementation with SQLAlchemy async,
SQL injection protection, read-only mode, and credential integration.
This is a placeholder that returns an error until properly implemented.
"""

from typing import Any


async def database_handler(args: dict, config: dict, state: dict) -> dict:
    """Execute a database query.

    Args:
        args: Resolved input parameters from upstream nodes
        config: Node configuration (DatabaseNodeData fields)
        state: LangGraph state

    Returns:
        Structured output dict with columns, rows, row_count.
    """
    # TODO: Phase 4 — full implementation
    # 1. Resolve credential_id → get connection info
    # 2. Create async SQLAlchemy engine
    # 3. Execute SQL with parameterized query
    # 4. Apply read_only check (reject DDL/DML)
    # 5. Limit max_rows
    # 6. Return structured result

    raise NotImplementedError(
        "Database node is not yet implemented. "
        "It will be available in Phase 4 with PostgreSQL + MySQL support."
    )
