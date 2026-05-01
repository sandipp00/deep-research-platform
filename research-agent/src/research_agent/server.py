"""FastAPI server — Redis lifespan + POST /research SSE endpoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import coloredlogs
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator

from research_agent.config import get_settings
from research_agent.http_handler import ResearchRequest, stream_research
from research_agent.infrastructure.redis_client import (
    connect_redis,
    disconnect_redis,
    get_redis,
)

settings = get_settings()
coloredlogs.install(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Alvoff Research Agent")
    await connect_redis()
    logger.info("Research Agent ready on port %d", settings.PORT)
    yield
    logger.info("Shutting down Research Agent")
    await disconnect_redis()
    logger.info("Research Agent stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Alvoff Research Agent",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Instrumentator().instrument(app).expose(app)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def health_ready():
        checks = {}
        try:
            await get_redis().ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {e}"
        checks["openrouter"] = "configured" if settings.OPENROUTER_API_KEY else "missing"
        checks["openai"] = "configured" if settings.OPENAI_API_KEY else "missing"
        checks["exa"] = "configured" if settings.EXA_API_KEY else "missing"
        checks["tavily"] = "configured" if settings.TAVILY_API_KEY else "missing"

        llm_ok = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
        search_ok = settings.EXA_API_KEY or settings.TAVILY_API_KEY
        all_ok = checks["redis"] == "ok" and llm_ok and search_ok
        return JSONResponse(
            content={"status": "ready" if all_ok else "degraded", "checks": checks},
            status_code=200 if all_ok else 503,
        )

    @app.post("/research", tags=["research"])
    async def research(req: ResearchRequest):
        """Stream research progress as SSE.

        Events: `checkpoint` (progress), `blocks` (final blocks), `clarification`,
        `error`, `done`.
        """
        return StreamingResponse(
            stream_research(req),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
