import uvicorn

from research_agent.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "research_agent.server:create_app",
        factory=True,
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
