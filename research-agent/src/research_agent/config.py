import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8004
    LOG_LEVEL: str = "INFO"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # LLM — OpenRouter primary
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "deepseek/deepseek-v4.1-flash"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_TEMPERATURE: float = 0.3

    # LLM — OpenAI fallback
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Octen (primary web search)
    OCTEN_API_KEY: str = ""
    OCTEN_MAX_RESULTS: int = 5

    # Tavily (fallback web search)
    TAVILY_API_KEY: str = ""
    TAVILY_MAX_RESULTS: int = 5
    TAVILY_SEARCH_DEPTH: str = "advanced"

    # Jina Reader (optional — free tier works without key)
    JINA_API_KEY: str = ""

    # LangSmith (optional — tracing/eval for the LangGraph agent)
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "lumen-research-agent"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # LangChain reads tracing config from os.environ directly, not from our
    # Settings object — propagate it here once, right after load, so every
    # module that imports get_settings() gets tracing for free with no
    # separate bootstrap step.
    if settings.LANGCHAIN_TRACING_V2 and settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT

    return settings
