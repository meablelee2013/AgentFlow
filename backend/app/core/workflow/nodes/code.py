"""Code node executor — run Python in Docker sandbox.

Phase 5 will add full Docker sandbox execution with:
- async def main(args): entry point (Coze standard)
- Resource limits (CPU, memory, timeout)
- Network isolation
- Temporary container lifecycle

This is a placeholder that returns an error until properly implemented.
"""

from typing import Any


async def code_handler(args: dict, config: dict, state: dict) -> dict:
    """Execute Python code in a sandboxed environment.

    Args:
        args: Resolved input parameters from upstream nodes
        config: Node configuration (CodeNodeData fields)
        state: LangGraph state

    Returns:
        Dict returned by the user's main(args) function.
    """
    # TODO: Phase 5 — Docker sandbox implementation
    # 1. Serialize args to JSON
    # 2. Write user code + runner to temp directory
    # 3. docker run --rm --network=none --memory=256m python:3.12-slim
    # 4. Read output.json
    # 5. Return parsed result

    raise NotImplementedError(
        "Code execution node is not yet implemented. "
        "It will be available in Phase 5 with Docker sandbox support."
    )
