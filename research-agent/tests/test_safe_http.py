import functools

import httpx
import pytest

from research_agent.agent import safe_http, tools

PUBLIC_IP = "93.184.216.34"

DNS = {
    "example.com": [PUBLIC_IP],
    "r.jina.ai": ["104.18.0.1"],
    "docs.example.com": [PUBLIC_IP],
    "internal.example.com": ["10.1.2.3"],
    "mixed.example.com": [PUBLIC_IP, "127.0.0.1"],
    "v6local.example.com": ["::1"],
    "metadata.example.com": ["169.254.169.254"],
}


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    calls = []

    async def resolver(host, port):
        calls.append(host)
        if host not in DNS:
            raise OSError("no such host")
        return DNS[host]

    monkeypatch.setattr(safe_http, "_getaddrinfo", resolver)
    return calls


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://127.1.2.3:8080/admin",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[fe80::1]/",
        "http://[fd00::1]/",
        "http://0.0.0.0/",
        "http://100.64.0.1/",
        "http://localhost:8004/research",
        "http://foo.localhost/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "ftp://example.com/file",
        "gopher://example.com/",
        "http://user:pass@example.com/",
        "not a url",
    ],
)
def test_check_url_blocks(url):
    with pytest.raises(safe_http.BlockedURLError):
        safe_http.check_url(url)


def test_check_url_allows_public():
    assert safe_http.check_url("https://example.com/a.pdf").host == "example.com"


@pytest.mark.parametrize(
    "url",
    [
        "http://internal.example.com/",
        "http://mixed.example.com/",
        "http://v6local.example.com/",
        "http://metadata.example.com/latest/",
        "http://unknown.example.com/",
    ],
)
async def test_validate_url_blocks_private_resolution(url):
    with pytest.raises(safe_http.BlockedURLError):
        await safe_http.validate_url(url)


async def test_validate_url_allows_public_resolution():
    await safe_http.validate_url("https://example.com/page")


async def test_safe_get_pins_resolved_ip_and_sets_host():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, text="hello")

    res = await safe_http.safe_get(
        "http://example.com/page", max_bytes=1000, transport=httpx.MockTransport(handler)
    )
    assert res.text == "hello"
    assert seen[0].url.host == PUBLIC_IP
    assert seen[0].headers["host"] == "example.com"


@pytest.mark.parametrize(
    "location",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1:6379/",
        "http://[::1]/",
        "http://internal.example.com/secret",
        "file:///etc/passwd",
    ],
)
async def test_safe_get_blocks_redirect_to_private(location):
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": location})

    with pytest.raises(safe_http.BlockedURLError):
        await safe_http.safe_get(
            "http://example.com/start", max_bytes=1000, transport=httpx.MockTransport(handler)
        )
    assert len(seen) == 1


async def test_safe_get_follows_public_redirect():
    def handler(request: httpx.Request):
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "https://docs.example.com/final"})
        return httpx.Response(200, text="final")

    res = await safe_http.safe_get(
        "http://example.com/start", max_bytes=1000, transport=httpx.MockTransport(handler)
    )
    assert res.text == "final"
    assert res.url == "https://docs.example.com/final"


async def test_safe_get_redirect_loop_is_capped():
    def handler(request: httpx.Request):
        return httpx.Response(302, headers={"location": "/again"})

    with pytest.raises(safe_http.BlockedURLError):
        await safe_http.safe_get(
            "http://example.com/", max_bytes=1000, max_redirects=3, transport=httpx.MockTransport(handler)
        )


async def test_safe_get_caps_body_size():
    def handler(request: httpx.Request):
        return httpx.Response(200, content=b"x" * 5000)

    with pytest.raises(safe_http.ResponseTooLargeError):
        await safe_http.safe_get("http://example.com/", max_bytes=1000, transport=httpx.MockTransport(handler))


async def test_safe_get_rejects_large_content_length():
    def handler(request: httpx.Request):
        return httpx.Response(200, content=b"x", headers={"content-length": "999999999"})

    with pytest.raises(safe_http.ResponseTooLargeError):
        await safe_http.safe_get("http://example.com/", max_bytes=1000, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.8/report.pdf",
        "http://169.254.169.254/latest/meta-data/iam/",
        "http://[::1]:8004/",
        "file:///etc/passwd",
        "http://internal.example.com/x.pdf",
    ],
)
async def test_read_webpage_returns_blocked_result(url, memory_cache):
    out = await tools.read_webpage.ainvoke({"url": url})
    assert out.startswith("Blocked URL:")
    assert memory_cache == {}


async def test_read_webpage_pdf_redirect_to_private_is_blocked(monkeypatch, memory_cache):
    requested = []

    def handler(request: httpx.Request):
        requested.append(request.headers["host"])
        if request.headers["host"] == "r.jina.ai":
            return httpx.Response(500)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    monkeypatch.setattr(
        safe_http, "safe_get",
        functools.partial(safe_http.safe_get, transport=httpx.MockTransport(handler)),
    )
    out = await tools.read_webpage.ainvoke({"url": "https://docs.example.com/report.pdf"})
    assert out.startswith("Blocked URL:")
    assert "169.254.169.254" not in requested
    assert memory_cache == {}


async def test_read_webpage_success_is_cached(monkeypatch, memory_cache):
    body = "Article text. " * 50

    def handler(request: httpx.Request):
        assert request.headers["host"] == "r.jina.ai"
        return httpx.Response(200, text=body)

    monkeypatch.setattr(
        safe_http, "safe_get",
        functools.partial(safe_http.safe_get, transport=httpx.MockTransport(handler)),
    )
    out = await tools.read_webpage.ainvoke({"url": "https://example.com/article"})
    assert out == body[:8000]
    assert list(memory_cache.values()) == [out]
