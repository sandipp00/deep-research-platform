from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_JWT_SECRET = "change-me-in-prod-use-a-long-random-string-at-least-32-bytes"


class InsecureConfigError(RuntimeError):
    pass


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://alvoff:alvoff@localhost:5433/alvoff"
    jwt_secret: str = ""
    jwt_expiration_minutes: int = 60 * 24
    research_agent_url: str = "http://localhost:8004"
    cors_allowed_origins: str = "http://localhost:5173"
    cors_dev_localhost: bool = True
    port: int = 8080

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    def ensure_secure(self) -> None:
        secret = (self.jwt_secret or "").strip()
        if not secret:
            raise InsecureConfigError(
                "JWT_SECRET is not set. Refusing to start. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if secret == INSECURE_DEFAULT_JWT_SECRET or secret.lower().startswith("change-me"):
            raise InsecureConfigError(
                "JWT_SECRET is set to the insecure placeholder value. Refusing to start. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )


settings = Settings()
