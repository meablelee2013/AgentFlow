"""Customer Service API endpoints."""
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.engine.cs_nodes import api_call_node

router = APIRouter(prefix="/customer-service", tags=["customer-service"])


class APICallTestRequest(BaseModel):
    """Request to test an external API call."""
    url: str
    method: str = "GET"
    headers: dict[str, str] = {}
    query_params: dict[str, str] = {}
    body: Any = None
    response_path: Optional[str] = None
    timeout: int = 30
    retry_count: int = 0


class APICallTestResponse(BaseModel):
    status: Optional[int] = None
    body: Any = None
    headers: dict[str, str] = {}
    duration_ms: int = 0
    retries_used: int = 0
    error: Optional[str] = None


@router.post("/test-api-call", response_model=APICallTestResponse)
async def test_api_call(request: APICallTestRequest):
    """Test an external API call with arbitrary configuration.

    Use this endpoint to debug api_call_node with any URL / method / headers.
    Great for testing new API integrations before wiring them into the engine.
    """
    result = await api_call_node(request.model_dump())
    return result