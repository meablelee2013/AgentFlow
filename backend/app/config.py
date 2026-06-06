"""AgentFlow application config — reads from .env and system environment variables"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings

    Priority: system env vars > .env file > defaults
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "AgentFlow"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://agentflow:agentflow@localhost:5434/agentflow"
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

    # --- Vector Storage ---
    VECTOR_DIMENSION: int = 1536


settings = Settings()
