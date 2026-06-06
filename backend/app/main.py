"""AgentFlow API — FastAPI application entrypoint

Request lifecycle:
    Request → CORS Middleware → Router → Response
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings
from app.api.v1.chat import router as chat_router

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Resource management on startup/shutdown"""
    logger.info("AgentFlow starting", version=settings.APP_VERSION)
    yield
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


@app.get("/health")
async def health_check():
    """Health check endpoint — usable as K8s liveness probe"""
    return {"status": "ok", "version": settings.APP_VERSION}
