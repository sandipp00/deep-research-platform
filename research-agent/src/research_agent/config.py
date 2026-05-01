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
    OPENROUTER_MODEL: str = "anthropic/claude-sonnet-4-6"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_TEMPERATURE: float = 0.3

    # LLM — OpenAI fallback
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Exa (primary web search)
    EXA_API_KEY: str = ""
    EXA_MAX_RESULTS: int = 5

    # Tavily (fallback web search)
    TAVILY_API_KEY: str = ""
    TAVILY_MAX_RESULTS: int = 5
    TAVILY_SEARCH_DEPTH: str = "advanced"

    # Jina Reader (optional — free tier works without key)
    JINA_API_KEY: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
