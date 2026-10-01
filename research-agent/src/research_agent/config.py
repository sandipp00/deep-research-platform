import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    HOST: str = "0.0.0.0"
    PORT: int = 8004
    LOG_LEVEL: str = "INFO"

    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:8080"

    MAX_QUERY_CHARS: int = 4000
    MAX_HISTORY_MESSAGES: int = 20
    MAX_HISTORY_MESSAGE_CHARS: int = 16000
    REQUEST_TIMEOUT_SECONDS: float = 180.0
    AGENT_RECURSION_LIMIT: int = 40

    REDIS_URL: str = "redis://localhost:6379"

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "deepseek/deepseek-v4.1-flash"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_TEMPERATURE: float = 0.3

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    FOLLOW_UP_MODEL: str = ""

    OCTEN_API_KEY: str = ""
    OCTEN_MAX_RESULTS: int = 5

    TAVILY_API_KEY: str = ""
    TAVILY_MAX_RESULTS: int = 5
    TAVILY_SEARCH_DEPTH: str = "advanced"

    JINA_API_KEY: str = ""

    WEBPAGE_MAX_BYTES: int = 5 * 1024 * 1024

    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "lumen-research-agent"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def agent_model_name(self) -> str:
        if self.OPENROUTER_API_KEY:
            return self.OPENROUTER_MODEL
        if self.OPENAI_API_KEY:
            return self.OPENAI_MODEL
        return ""


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    return settings
