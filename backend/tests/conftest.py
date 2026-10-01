import asyncio
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import psycopg
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

PG_HOST = os.environ.get("TEST_PG_HOST", "localhost")
PG_PORT = os.environ.get("TEST_PG_PORT", "5433")
PG_USER = os.environ.get("TEST_PG_USER", "alvoff")
PG_PASSWORD = os.environ.get("TEST_PG_PASSWORD", "alvoff")
PG_ADMIN_DB = os.environ.get("TEST_PG_ADMIN_DB", "alvoff")
TEST_DB = os.environ.get("TEST_PG_DB", "alvoff_test")
TEST_JWT_SECRET = "test-secret-0123456789-abcdefghijklmnopqrstuvwxyz"
LEAK_MARKER = "SECRET-INTERNAL-DETAIL-xyz"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


AGENT_PORT = _free_port()
BACKEND_PORT = _free_port()

os.environ["DATABASE_URL"] = f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{TEST_DB}"
os.environ["JWT_SECRET"] = TEST_JWT_SECRET
os.environ["RESEARCH_AGENT_URL"] = f"http://127.0.0.1:{AGENT_PORT}"


def _ensure_test_database() -> None:
    conninfo = f"host={PG_HOST} port={PG_PORT} user={PG_USER} password={PG_PASSWORD} dbname={PG_ADMIN_DB}"
    with psycopg.connect(conninfo, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB}"')


_ensure_test_database()

AGENT_REQUESTS: list[dict] = []


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


OK_BLOCKS = {
    "data": {
        "blocks": [{"template_id": "markdown", "data": {"content": "Final answer text"}}],
        "sources": [{"url": "https://example.com/a", "title": "A", "snippet": "s"}, "https://example.com/b"],
        "follow_ups": ["What next?"],
    }
}


def build_fake_agent() -> FastAPI:
    agent = FastAPI()

    @agent.post("/research")
    async def research(request: Request):
        body = await request.json()
        AGENT_REQUESTS.append(body)
        query = body.get("query", "")

        if query == "http500":
            return PlainTextResponse(f"boom {LEAK_MARKER}", status_code=500)

        async def stream():
            yield _frame("progress", {"status": "searching"})
            if query == "agent-error":
                yield _frame("error", {"status": "failed", "content": "Agent could not complete"})
                return
            if query == "clarify":
                yield _frame("clarification", {"content": "Which one do you mean?"})
                return
            yield _frame("blocks", OK_BLOCKS)
            if query == "slow":
                for _ in range(300):
                    if await request.is_disconnected():
                        return
                    await asyncio.sleep(0.1)
                return
            yield _frame("done", {"status": "complete"})

        return StreamingResponse(stream(), media_type="text/event-stream")

    return agent


class _ThreadedServer:
    def __init__(self, app, port: int) -> None:
        config = uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", lifespan="on", timeout_graceful_shutdown=2
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        deadline = time.time() + 15
        while not self.server.started:
            if time.time() > deadline or not self.thread.is_alive():
                raise RuntimeError("test server failed to start")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


@pytest.fixture(scope="session")
def app():
    from app.db import Base, engine
    from app.main import app as fastapi_app

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield fastapi_app
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="session")
def fake_agent():
    server = _ThreadedServer(build_fake_agent(), AGENT_PORT)
    server.start()
    yield f"http://127.0.0.1:{AGENT_PORT}"
    server.stop()


@pytest.fixture(scope="session")
def live_backend(app, fake_agent):
    server = _ThreadedServer(app, BACKEND_PORT)
    server.start()
    yield f"http://127.0.0.1:{BACKEND_PORT}"
    server.stop()


@pytest.fixture(autouse=True)
def clean_db(app):
    from app.db import engine
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE messages, conversations, users CASCADE"))
    AGENT_REQUESTS.clear()
    yield


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def register(client, email: str, password: str = "password123", name: str = "Tester") -> dict:
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 200, r.text
    return r.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
