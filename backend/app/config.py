from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://alvoff:alvoff@localhost:5433/alvoff"
    jwt_secret: str = "change-me-in-prod-use-a-long-random-string-at-least-32-bytes"
    jwt_expiration_minutes: int = 60 * 24
    research_agent_url: str = "http://localhost:8004"
    cors_allowed_origins: str = "http://localhost:5173"
    port: int = 8080

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


settings = Settings()
