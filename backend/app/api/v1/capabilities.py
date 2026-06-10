"""Capabilities API — expose the global executor capability registry."""

from fastapi import APIRouter
from app.core.workflow.capability_registry import get_capability_registry

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("")
async def list_capabilities():
    """List all available executor capabilities (builtin nodes + agents).

    The Decompose node's config panel calls this to show checkboxes.
    Each capability includes id, type, label, description, and input_schema.

    Returns:
        {
            "builtin_nodes": [{id, type, label, description, input_schema}, ...],
            "agents": [{id, type, label, description, input_schema, tools}, ...]
        }
    """
    registry = get_capability_registry()
    return registry.to_api_response()
