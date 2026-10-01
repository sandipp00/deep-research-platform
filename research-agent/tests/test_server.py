import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from research_agent import http_handler
from research_agent.infrastructure.redis_client import mask_url
from research_agent.server import create_app


class OneShotAgent:
    async def astream_events(self, *args, **kwargs):
        yield {"event": "on_chat_model_end", "data": {"output": AIMessage(content="Hi.")}}


@pytest.fixture
def client(monkeypatch):
    async def get_agent():
        return OneShotAgent()

    monkeypatch.setattr(http_handler, "get_agent", get_agent)
    return TestClient(create_app())


@pytest.mark.parametrize(
    "body",
    [
        {"query": "x" * 4001},
        {"query": ""},
        {"query": "   "},
        {"query": "ok", "conversation_history": [{"role": "user", "content": "m"}] * 21},
        {"query": "ok", "conversation_history": [{"role": "user", "content": "m" * 16001}]},
        {"query": "ok", "conversation_history": [{"role": "u" * 33, "content": "m"}]},
        {},
    ],
)
def test_input_limits_return_422(client, body):
    assert client.post("/research", json=body).status_code == 422


def test_limits_are_configurable(client, settings, monkeypatch):
    monkeypatch.setattr(settings, "MAX_QUERY_CHARS", 10)
    assert client.post("/research", json={"query": "x" * 11}).status_code == 422
    assert client.post("/research", json={"query": "x" * 10}).status_code == 200


def test_valid_request_streams_and_ends_with_done(client):
    body = {"query": "x" * 4000, "conversation_history": [{"role": "user", "content": "m" * 16000}] * 20}
    resp = client.post("/research", json=body)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    blocks = [b for b in resp.text.split("\n\n") if b.strip()]
    assert blocks[-1].startswith("event: done\n")
    done = json.loads(blocks[-1].split("data: ", 1)[1])
    assert done["status"] == "completed"
    assert "metrics" in done


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/research", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
    })
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/research", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in bad.headers


def test_startup_survives_redis_down(monkeypatch):
    with TestClient(create_app()) as c:
        assert c.get("/health").json() == {"status": "ok"}
        ready = c.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"]["redis"].startswith("error")


@pytest.mark.parametrize(
    "url,expected",
    [
        ("redis://:s3cret@redis:6379/0", "redis://:***@redis:6379/0"),
        ("redis://user:s3cret@redis:6379", "redis://user:***@redis:6379"),
        ("redis://localhost:6379", "redis://localhost:6379"),
    ],
)
def test_mask_url(url, expected):
    assert mask_url(url) == expected
