"""AgentFlow 应用配置 — 从 .env 和系统环境变量读取"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置

    优先级: 系统环境变量 > .env 文件 > 默认值
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 应用 ---
    APP_NAME: str = "AgentFlow"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # --- 数据库 ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://agentflow:agentflow@localhost:5432/agentflow"
    )

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- LLM ---
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # --- Embedding ---
    EMBEDDING_MODEL: str = "deepseek-chat"

    # --- 向量存储 ---
    VECTOR_DIMENSION: int = 1536


settings = Settings()
