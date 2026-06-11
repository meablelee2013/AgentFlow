"""AgentFlow API — FastAPI application entrypoint

Request lifecycle:
    Request → CORS Middleware → Router → Response
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import structlog

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
    """Resource management on startup/shutdown"""
    logger.info("AgentFlow starting", version=settings.APP_VERSION)
    from app.core.engine.checkpoint import CheckpointerManager
    CheckpointerManager.init_postgres()
    yield
    CheckpointerManager.shutdown()
    logger.info("AgentFlow shutting down")


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


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint.

    Exposes LLM call metrics (QPS, P99 latency, error counts) and
    agent loop guard metrics (verdicts, token ratio, confidence).

    Scrape this with Prometheus and visualize with the provided
    Grafana dashboard at deploy/grafana/dashboard.json.
    """
    if not settings.METRICS_ENABLED:
        return Response(content="Metrics disabled", status_code=404)
    from app.core.metrics import get_metrics
    return Response(content=get_metrics(), media_type="text/plain; charset=utf-8")
