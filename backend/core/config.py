"""
ElasticGuard Configuration
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "ElasticGuard"
    SECRET_KEY: str = "change-this-to-random-secret-key-32chars"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database (SQLite for local, Postgres for production)
    DATABASE_URL: str = "sqlite+aiosqlite:///./elasticguard.db"

    # Redis (optional, for task queues)
    REDIS_URL: Optional[str] = None

    # AI Providers
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_DEFAULT_MODEL: str = "gpt-4o"

    GEMINI_API_KEY: Optional[str] = None
    GEMINI_DEFAULT_MODEL: str = "gemini-2.0-flash-lite" #"gemini-2.0-flash"

    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_DEFAULT_MODEL: str = "claude-3-5-sonnet-20241022"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_MODEL: str = "llama3.2"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # Default AI provider
    DEFAULT_AI_PROVIDER: str = "openai"  # openai | gemini | anthropic | ollama | custom

    # Custom OpenAI-compatible endpoint
    CUSTOM_AI_BASE_URL: Optional[str] = None
    CUSTOM_AI_KEY: Optional[str] = None
    CUSTOM_AI_MODEL: Optional[str] = None

    # Notifications
    DISCORD_BOT_TOKEN: Optional[str] = None
    DISCORD_CHANNEL_ID: Optional[str] = None
    DISCORD_WEBHOOK_URL: Optional[str] = None

    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_CHANNEL_ID: Optional[str] = None
    SLACK_WEBHOOK_URL: Optional[str] = None

    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASS: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    NOTIFICATION_EMAILS: str = ""  # comma-separated

    # Approval
    APPROVAL_WEBHOOK_SECRET: str = "change-this-approval-secret"
    APPROVAL_TIMEOUT_MINUTES: int = 60

    # Monitoring
    MONITORING_INTERVAL_SECONDS: int = 30
    ALERT_CPU_THRESHOLD: float = 80.0
    ALERT_JVM_THRESHOLD: float = 85.0
    ALERT_DISK_THRESHOLD: float = 85.0

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    KNOWLEDGE_BASE_DIR: str = "./knowledge/docs"

    # CORS
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:3001"]


settings = Settings()
