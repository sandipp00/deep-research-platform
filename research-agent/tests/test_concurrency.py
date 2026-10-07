import asyncio
import threading
import time

import pytest

from research_agent.agent import tools

DELAY = 0.5


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, memory_cache):
    monkeypatch.setattr(tools.settings, "OCTEN_API_KEY", "")
    monkeypatch.setattr(tools.settings, "TAVILY_API_KEY", "")


def _slow(result):
    intervals = []
    lock = threading.Lock()

    def fn(*args, **kwargs):
        start = time.perf_counter()
        time.sleep(DELAY)
        with lock:
            intervals.append((start, time.perf_counter()))
        return result

    return fn, intervals


async def _ticker(stop: asyncio.Event, ticks: list):
    while not stop.is_set():
        ticks.append(time.perf_counter())
        await asyncio.sleep(0.02)


async def _run_with_ticker(*coros):
    stop = asyncio.Event()
    ticks: list = []
    ticker = asyncio.create_task(_ticker(stop, ticks))
    started = time.perf_counter()
    results = await asyncio.gather(*coros)
    elapsed = time.perf_counter() - started
    stop.set()
    await ticker
    return results, elapsed, ticks


def _overlap(intervals):
    (a0, a1), (b0, b1) = intervals
    return min(a1, b1) - max(a0, b0)


async def test_two_web_searches_overlap(monkeypatch):
    fn, intervals = _slow([{"title": "t", "body": "b", "href": "https://x.com"}])
    monkeypatch.setattr(tools, "_ddg_search_sync", fn)
    results, elapsed, ticks = await _run_with_ticker(
        tools.web_search.ainvoke({"query": "one"}),
        tools.web_search.ainvoke({"query": "two"}),
    )
    assert all("https://x.com" in r for r in results)
    assert len(intervals) == 2
    assert _overlap(intervals) > DELAY * 0.6
    assert elapsed < DELAY * 1.8
    assert len(ticks) >= 10


async def test_mixed_sync_and_async_tools_overlap(monkeypatch):
    wiki_fn, wiki_iv = _slow("Summary text")
    stock_iv = []

    async def chart(client, sym):
        start = time.perf_counter()
        await asyncio.sleep(DELAY)
        stock_iv.append((start, time.perf_counter()))
        return {"regularMarketPrice": 100.0, "previousClose": 99.0, "currency": "USD"}

    monkeypatch.setattr(tools, "_wiki_lookup_sync", wiki_fn)
    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    results, elapsed, ticks = await _run_with_ticker(
        tools.wiki_search.ainvoke({"query": "Python"}),
        tools.get_stock_price.ainvoke({"symbol": "AAPL.US"}),
    )
    assert results[0] == "Summary text"
    assert results[1].startswith("STOCK|AAPL.US|100.0")
    assert _overlap(wiki_iv + stock_iv) > DELAY * 0.6
    assert elapsed < DELAY * 1.8
    assert len(ticks) >= 10



class _HangingOverpassClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return [{"lat": "12.9", "lon": "77.6"}]

        return Resp()

    async def post(self, url, **kwargs):
        await asyncio.sleep(30)


async def test_overpass_deadline_returns_error_quickly(monkeypatch):
    monkeypatch.setattr(tools.httpx, "AsyncClient", _HangingOverpassClient)
    monkeypatch.setattr(tools, "_OVERPASS_DEADLINE_S", 0.3)
    start = time.perf_counter()
    out = await tools._nearby("Koramangala, Bengaluru", "cafe", 3000)
    elapsed = time.perf_counter() - start
    assert elapsed < 3
    assert out.status == "error"
    assert "Overpass" in out.text


class _MirrorClient:
    behaviors: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return [{"lat": "12.9", "lon": "77.6"}]

        return Resp()

    async def post(self, url, **kwargs):
        behavior = self.behaviors[url]
        if behavior == "hang":
            await asyncio.sleep(30)
        if behavior == "fail":
            raise RuntimeError("504")

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"elements": [{"type": "node", "lat": 12.91, "lon": 77.61, "tags": {"name": "Cafe One"}}]}

        return Resp()


async def test_overpass_mirrors_race_in_parallel(monkeypatch):
    a, b, c = tools._OVERPASS_MIRRORS
    _MirrorClient.behaviors = {a: "hang", b: "hang", c: "ok"}
    monkeypatch.setattr(tools.httpx, "AsyncClient", _MirrorClient)
    start = time.perf_counter()
    out = await tools._nearby("Koramangala, Bengaluru", "cafe", 3000)
    assert time.perf_counter() - start < 3
    assert out.status == "ok"
    assert "Cafe One" in out.text


async def test_overpass_failed_mirror_does_not_block_success(monkeypatch):
    a, b, c = tools._OVERPASS_MIRRORS
    _MirrorClient.behaviors = {a: "fail", b: "ok", c: "fail"}
    monkeypatch.setattr(tools.httpx, "AsyncClient", _MirrorClient)
    out = await tools._nearby("Koramangala, Bengaluru", "cafe", 3000)
    assert out.status == "ok"
