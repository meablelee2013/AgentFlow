"""AgentFlow API — FastAPI application entrypoint

Request lifecycle:
    Request → CORS Middleware → Router → Response
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog
import httpx

from app.config import settings
from app.api.v1.chat import router as chat_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.agent import router as agent_router
from app.api.v1.supervisor import router as supervisor_router
from app.api.v1.workflow import router as workflow_router
from app.api.v1.memory import router as memory_router
from app.api.v1.credential import router as credential_router
from app.api.v1.customer_service import router as customer_service_router
from app.api.v1.capabilities import router as capabilities_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Resource management on startup/shutdown.

    1. Initialize PostgreSQL checkpointer
    2. Connect to MCP servers defined in .mcp.json
    3. Yield (app runs)
    4. Shut down MCP connections and checkpointer
    """
    logger.info("AgentFlow starting", version=settings.APP_VERSION)

    # Initialize PostgreSQL checkpointer
    from app.core.engine.checkpoint import CheckpointerManager
    CheckpointerManager.init_postgres()

    # Initialize MCP client(s) from .mcp.json
    await _startup_mcp()

    yield

    # Shutdown MCP client(s)
    await _shutdown_mcp()

    CheckpointerManager.shutdown()
    logger.info("AgentFlow shutting down")


async def _startup_mcp() -> None:
    """Connect to MCP servers defined in .mcp.json.

    Uses streamable HTTP transport to connect to each server,
    discover tools, and cache them for request-time use.

    Graceful degradation: if MCP connection fails, the app
    still starts — just without MCP tools available.
    """
    from app.core.mcp.config import MCPConfig
    from app.core.mcp.client import get_mcp_client

    mcp_config = MCPConfig.from_project_root()
    if not mcp_config.servers:
        logger.info("mcp_no_servers_configured")
        return

    manager = get_mcp_client()

    for server in mcp_config.servers:
        logger.info(
            "mcp_connecting",
            server=server.name,
            url=server.url[:80] + "...",
        )
        try:
            # Create a shared HTTP client with reasonable timeouts
            http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=15.0),
            )

            # Import the streamable HTTP transport
            from mcp.client.streamable_http import streamable_http_client
            from mcp.client.session import ClientSession

            # Enter the transport context (must remain open for app lifetime)
            # We store the context managers so they can be exited at shutdown.
            transport_ctx = streamable_http_client(
                server.url,
                http_client=http_client,
                terminate_on_close=True,
            )
            read_stream, write_stream, _ = await transport_ctx.__aenter__()

            # Create and initialize the session
            session_ctx = ClientSession(read_stream, write_stream)
            session = await session_ctx.__aenter__()
            await session.initialize()

            # Store session and context managers for later cleanup
            manager._set_session(session)
            manager._transport_ctx = transport_ctx  # type: ignore[attr-defined]
            manager._session_ctx = session_ctx  # type: ignore[attr-defined]
            manager._http_client = http_client  # type: ignore[attr-defined]

            # Discover tools
            await manager.discover_tools()

            logger.info(
                "mcp_connected",
                server=server.name,
                tool_count=len(manager.tools),
            )
            # Only connect to the first server for now
            break

        except Exception:
            logger.exception(
                "mcp_connection_failed",
                server=server.name,
            )


async def _shutdown_mcp() -> None:
    """Clean up MCP connections."""
    from app.core.mcp.client import get_mcp_client

    manager = get_mcp_client()
    if not manager.is_initialized:
        return

    try:
        session_ctx = getattr(manager, "_session_ctx", None)
        transport_ctx = getattr(manager, "_transport_ctx", None)
        http_client = getattr(manager, "_http_client", None)

        if session_ctx is not None:
            await session_ctx.__aexit__(None, None, None)
        if transport_ctx is not None:
            await transport_ctx.__aexit__(None, None, None)
        if http_client is not None:
            await http_client.aclose()

        manager._clear_session()
        logger.info("mcp_shutdown_complete")
    except Exception:
        logger.exception("mcp_shutdown_error")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(chat_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(agent_router, prefix="/api/v1")
app.include_router(supervisor_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(credential_router, prefix="/api/v1")
app.include_router(customer_service_router, prefix="/api/v1")
app.include_router(capabilities_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint — usable as K8s liveness probe"""
    return {"status": "ok", "version": settings.APP_VERSION}
