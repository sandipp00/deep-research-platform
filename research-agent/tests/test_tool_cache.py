import httpx
import pytest

from research_agent.agent import tools
from research_agent.metrics import RequestMetrics, bind_metrics


@pytest.fixture(autouse=True)
def no_search_keys(monkeypatch):
    monkeypatch.setattr(tools.settings, "OCTEN_API_KEY", "")
    monkeypatch.setattr(tools.settings, "TAVILY_API_KEY", "")


@pytest.mark.parametrize(
    "output",
    [
        tools._error("Search failed: boom"),
        tools._empty("No results found."),
        tools._error("Could not fetch stock data for X: no price data available"),
        tools._error("Wikipedia lookup failed: timeout"),
        tools._empty("Coin 'nope' not found on CoinGecko."),
        tools._error("Overpass API unavailable on all mirrors: x"),
        tools._ok("   "),
    ],
)
async def test_cached_skips_non_success(memory_cache, output):
    async def fetch():
        return output

    assert await tools._cached("t", "k", 60, fetch) == output.text
    assert memory_cache == {}


async def test_cached_stores_success_and_hits(memory_cache):
    calls = []

    async def fetch():
        calls.append(1)
        return tools._ok("good data")

    metrics = RequestMetrics()
    bind_metrics(metrics)
    try:
        assert await tools._cached("t", "k", 60, fetch) == "good data"
        assert await tools._cached("t", "k", 60, fetch) == "good data"
    finally:
        bind_metrics(None)
    assert calls == [1]
    assert memory_cache == {"k": "good data"}
    assert [(r.cache_hit, r.success) for r in metrics.tools] == [(False, True), (True, True)]


async def test_cached_converts_exception_to_uncached_error(memory_cache):
    async def fetch():
        raise ValueError("kaput")

    out = await tools._cached("t", "k", 60, fetch)
    assert out.startswith("t failed: ValueError")
    assert memory_cache == {}


async def test_web_search_empty_not_cached(monkeypatch, memory_cache):
    monkeypatch.setattr(tools, "_ddg_search_sync", lambda q: [])
    assert await tools.web_search.ainvoke({"query": "q"}) == "No results found."
    assert memory_cache == {}


async def test_web_search_failure_not_cached(monkeypatch, memory_cache):
    def boom(q):
        raise RuntimeError("ratelimited")

    monkeypatch.setattr(tools, "_ddg_search_sync", boom)
    out = await tools.web_search.ainvoke({"query": "q"})
    assert out.startswith("Search failed")
    assert memory_cache == {}


async def test_web_search_success_cached_with_provider(monkeypatch, memory_cache):
    monkeypatch.setattr(tools, "_ddg_search_sync", lambda q: [{"title": "T", "body": "B", "href": "https://x.com"}])
    metrics = RequestMetrics()
    bind_metrics(metrics)
    try:
        out = await tools.web_search.ainvoke({"query": "q"})
    finally:
        bind_metrics(None)
    assert "https://x.com" in out
    assert list(memory_cache.values()) == [out]
    assert metrics.tools[0].provider == "duckduckgo"


async def test_tavily_empty_falls_through_to_duckduckgo(monkeypatch, memory_cache):
    monkeypatch.setattr(tools.settings, "TAVILY_API_KEY", "tvly-test")

    async def tavily(q):
        return []

    monkeypatch.setattr(tools, "_tavily_search", tavily)
    monkeypatch.setattr(tools, "_ddg_search_sync", lambda q: [{"title": "D", "body": "b", "href": "https://d.com"}])
    out = await tools._search("q")
    assert out.ok and out.provider == "duckduckgo"


async def test_octen_empty_falls_through_to_tavily(monkeypatch):
    monkeypatch.setattr(tools.settings, "OCTEN_API_KEY", "octen-test")
    monkeypatch.setattr(tools.settings, "TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(tools, "_octen_search_sync", lambda q: [])

    async def tavily(q):
        return [{"title": "T", "content": "c", "url": "https://t.com"}]

    monkeypatch.setattr(tools, "_tavily_search", tavily)
    out = await tools._search("q")
    assert out.ok and out.provider == "tavily"


async def test_wiki_failures_not_cached(monkeypatch, memory_cache):
    def boom(q):
        raise ConnectionError("down")

    monkeypatch.setattr(tools, "_wiki_lookup_sync", boom)
    assert (await tools.wiki_search.ainvoke({"query": "x"})).startswith("Wikipedia lookup failed")
    monkeypatch.setattr(tools, "_wiki_lookup_sync", lambda q: None)
    assert (await tools.wiki_search.ainvoke({"query": "x"})).startswith("No Wikipedia article found")
    assert memory_cache == {}


async def test_stock_no_data_not_cached(monkeypatch, memory_cache):
    async def chart(client, sym):
        raise tools.SymbolNotFound(sym)

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    out = await tools.get_stock_price.ainvoke({"symbol": "ZZZZ"})
    assert out.startswith("Could not fetch stock data")
    assert memory_cache == {}


def _mock_async_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(tools.httpx, "AsyncClient", factory)


async def test_crypto_not_found_not_cached(monkeypatch, memory_cache):
    _mock_async_client(monkeypatch, lambda r: httpx.Response(200, json={}))
    out = await tools.get_crypto_price.ainvoke({"coin_id": "nope"})
    assert out == "Coin 'nope' not found on CoinGecko."
    assert memory_cache == {}


async def test_forex_http_error_not_cached(monkeypatch, memory_cache):
    _mock_async_client(monkeypatch, lambda r: httpx.Response(503))
    out = await tools.get_forex_rate.ainvoke({"from_currency": "usd", "to_currency": "inr"})
    assert out.startswith("Could not fetch exchange rate for USD/INR")
    assert memory_cache == {}


async def test_latest_news_follows_redirects_checks_status_and_escapes(monkeypatch, memory_cache):
    rss = (
        "<?xml version='1.0'?><rss version='2.0'><channel><title>c</title>"
        "<item><title>RBI | repo rate cut</title><link>https://n.com/a</link>"
        "<pubDate>Tue, 01 Oct 2026 10:00:00 GMT</pubDate></item>"
        "</channel></rss>"
    )

    def handler(request: httpx.Request):
        if "feedburner" in request.url.host:
            return httpx.Response(301, headers={"location": "https://feeds.example.com/ndtv.xml"})
        if request.url.host == "feeds.example.com":
            return httpx.Response(200, text=rss)
        if "moneycontrol" in request.url.host:
            return httpx.Response(500, text=rss)
        return httpx.Response(200, text="<rss><channel></channel></rss>")

    _mock_async_client(monkeypatch, handler)
    out = await tools.latest_news.ainvoke({"topic": "RBI"})
    news = [line for line in out.splitlines() if line.startswith("NEWS|")]
    assert len(news) == 1
    parts = news[0].split("|")
    assert len(parts) == 5
    assert parts[1] == "RBI / repo rate cut"
    assert parts[2] == "NDTV"


async def test_nearby_places_escapes_pipes_and_sanitizes(monkeypatch, memory_cache):
    queries = []

    def handler(request: httpx.Request):
        if "nominatim" in request.url.host:
            return httpx.Response(200, json=[{"lat": "12.9", "lon": "77.6"}])
        queries.append(request.content.decode())
        return httpx.Response(200, json={"elements": [
            {"type": "node", "lat": 12.91, "lon": 77.61,
             "tags": {"name": "Shell | Express", "addr:street": "MG|Road"}},
        ]})

    _mock_async_client(monkeypatch, handler)
    out = await tools.nearby_places.ainvoke({"place": "Bangalore", "place_type": "fuel"})
    place = [line for line in out.splitlines() if line.startswith("PLACE|")][0]
    from research_agent.blocks.block_formatter import parse_place_line

    p = parse_place_line(place)
    assert p.name == "Shell / Express" and p.address == "MG/Road" and p.distance.endswith("km")
    sent = len(queries)
    assert sent >= 1

    bad = await tools.nearby_places.ainvoke({"place": "Bangalore", "place_type": 'fuel"](around:1,0,0);out;("'})
    assert bad.startswith("Unsupported place type")
    assert len(queries) == sent


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("RELIANCE", ["RELIANCE", "RELIANCE.NS"]),
        ("tcs.ns", ["TCS.NS"]),
        ("500325.BO", ["500325.BO"]),
        ("^NSEI", ["^NSEI"]),
        ("Nifty 50", ["^NSEI"]),
        ("sensex", ["^BSESN"]),
        ("EURUSD=X", ["EURUSD=X"]),
    ],
)
def test_stock_candidates(symbol, expected):
    assert tools.stock_candidates(symbol) == expected


@pytest.mark.parametrize(
    "place_type,expected",
    [
        ("fuel", ("amenity", "fuel")),
        ("EV Charging", ("amenity", "charging_station")),
        ("post-office", ("amenity", "post_office")),
        ("dentist", ("amenity", "dentist")),
        ('cafe"];node(1)', None),
        ("a" * 50, None),
    ],
)
def test_osm_tag_for(place_type, expected):
    assert tools.osm_tag_for(place_type) == expected
