"""AgentFlow API — FastAPI 应用入口

请求生命周期:
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
    """应用启动/关闭时的资源管理"""
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
    """健康检查端点 — 可用于 K8s liveness probe"""
    return {"status": "ok", "version": settings.APP_VERSION}
