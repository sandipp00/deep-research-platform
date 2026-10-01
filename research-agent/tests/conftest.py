import ipaddress
import os
import socket

import pytest

for _key in (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "OCTEN_API_KEY",
    "TAVILY_API_KEY",
    "JINA_API_KEY",
    "LANGCHAIN_API_KEY",
    "FOLLOW_UP_MODEL",
):
    os.environ[_key] = ""
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:5173,http://localhost:8080"

_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo


def _is_local(host) -> bool:
    if host in (None, "localhost", "testserver"):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else None
    if isinstance(address, tuple) and not _is_local(host):
        raise RuntimeError(f"real network access blocked in tests: {address!r}")
    return _real_connect(self, address)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_local(host):
        raise RuntimeError(f"real DNS lookup blocked in tests: {host!r}")
    return _real_getaddrinfo(host, *args, **kwargs)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
    yield


@pytest.fixture
def settings():
    from research_agent.config import get_settings

    return get_settings()


@pytest.fixture
def memory_cache(monkeypatch):
    from research_agent.agent import tools

    store: dict[str, str] = {}

    async def fake_get(key):
        return store.get(key)

    async def fake_set(key, value, ttl):
        store[key] = value

    monkeypatch.setattr(tools, "cache_get", fake_get)
    monkeypatch.setattr(tools, "cache_set", fake_set)
    return store
