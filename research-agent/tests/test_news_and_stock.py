import asyncio
import time
from email.utils import format_datetime
from datetime import datetime, timezone, timedelta

import httpx
import pytest

from research_agent.agent import tools
from research_agent.blocks.block_formatter import ToolResult, _parse_financial_card


def _rfc822(dt: datetime) -> str:
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


NOW = datetime.now(timezone.utc)


def _rss(items: list[tuple[str, str, datetime | None]], source: str | None = None) -> str:
    body = []
    for title, link, published in items:
        pub = f"<pubDate>{_rfc822(published)}</pubDate>" if published else ""
        src = f"<source url='https://pub.example'>{source}</source>" if source else ""
        body.append(f"<item><title>{title}</title><link>{link}</link>{pub}{src}<description>d</description></item>")
    return f"<?xml version='1.0'?><rss version='2.0'><channel><title>c</title>{''.join(body)}</channel></rss>"


def _mock_async_client(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(tools.httpx, "AsyncClient", factory)


def _article(title, ts=None, summary="", google=False, source="S", link="https://x/1"):
    return {
        "title": title, "summary": summary, "source": source, "published": "p",
        "ts": ts if ts is not None else NOW.timestamp(), "link": link, "google": google,
    }


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("Latest cricket news", ["cricket"]),
        ("Top technology news in India today", ["technology", "india"]),
        ("Latest news about the Indian stock market", ["indian", "stock", "market"]),
        ("RBI interest rate", ["rbi", "interest", "rate"]),
        ("latest news today", []),
        ("What's the latest on GST?", ["gst"]),
        ("S&P 500 news", ["s&p", "500"]),
        ("rbi RBI Rbi", ["rbi"]),
    ],
)
def test_news_keywords_strip_filler(topic, expected):
    assert tools.news_keywords(topic) == expected


def test_keyword_pattern_is_word_boundary_and_plural_aware():
    pat = tools._keyword_pattern("rate")
    assert pat.search("Repo RATES unchanged")
    assert pat.search("rate cut")
    assert not pat.search("corporate earnings")
    assert not pat.search("generated")
    assert tools._keyword_pattern("stocks").search("one stock rallies")
    assert tools._keyword_pattern("india").search("Indian markets")
    assert not tools._keyword_pattern("ai").search("said the chairman")


def test_rank_prefers_all_keywords_then_recency():
    now = NOW.timestamp()
    arts = [
        _article("Rate outlook for banks", now - 10, link="1"),
        _article("RBI holds interest rate steady", now - 3600, link="2"),
        _article("RBI interest rate decision today", now - 60, link="3"),
        _article("RBI governor speaks on rate path", now - 5, link="4"),
        _article("Cricket final tonight", now, link="5"),
        _article("Interest in gold rises", now - 1, link="6"),
    ]
    ranked, full = tools.rank_articles(["rbi", "interest", "rate"], [(arts, frozenset())], now)
    assert [a["link"] for a in ranked] == ["3", "2", "4"]
    assert full == 2


def test_rank_weak_keywords_cannot_qualify_alone_and_dedupes():
    now = NOW.timestamp()
    arts = [
        _article("India wins the match", now, link="1"),
        _article("Technology layoffs rise", now - 50, link="2"),
        _article("India technology exports grow", now - 100, link="3"),
        _article("India technology exports grow!", now - 10, link="4"),
    ]
    ranked, full = tools.rank_articles(["technology", "india"], [(arts, frozenset())], now)
    assert [a["link"] for a in ranked] == ["4", "2"]
    assert full == 2


def test_rank_credits_topic_feed_and_drops_stale():
    now = NOW.timestamp()
    feed = [
        _article("Kohli scores century", now - 10, link="1"),
        _article("Ancient result", now - 400 * 86400, link="2"),
    ]
    ranked, full = tools.rank_articles(["cricket"], [(feed, frozenset({"cricket"}))], now)
    assert [a["link"] for a in ranked] == ["1"]
    assert full == 1


def test_rank_google_items_need_only_one_keyword():
    now = NOW.timestamp()
    g = [_article("RBI policy preview", now, google=True, link="g")]
    r = [_article("RBI policy preview from a feed", now, link="r")]
    ranked, _ = tools.rank_articles(["rbi", "interest", "rate"], [(r, frozenset()), (g, frozenset())], now)
    assert [a["link"] for a in ranked] == ["g"]


def test_feeds_for_adds_topic_feeds_with_credit():
    feeds = tools._feeds_for(["cricket"])
    urls = {u: c for _, u, c in feeds}
    for _, u in tools._RSS_FEEDS:
        assert urls[u] == frozenset()
    for _, u in tools._TOPIC_FEEDS["cricket"]:
        assert urls[u] == frozenset({"cricket"})
    ipl = {u: c for _, u, c in tools._feeds_for(["ipl"])}
    assert all(ipl[u] == frozenset() for _, u in tools._TOPIC_FEEDS["cricket"])
    assert len(tools._feeds_for(["gst"])) == len(tools._RSS_FEEDS)


def test_parse_google_feed_splits_publisher_suffix():
    text = _rss(
        [
            ("RBI hikes repo rate - Reuters", "https://news.google.com/a", NOW),
            ("Markets slide - Mint - Livemint", "https://news.google.com/b", NOW),
        ],
        source="Reuters",
    )
    arts = tools._parse_feed_sync(text, "Google News", google=True)
    assert arts[0]["title"] == "RBI hikes repo rate"
    assert arts[0]["source"] == "Reuters"
    assert arts[0]["link"] == "https://news.google.com/a"
    assert arts[0]["ts"] > 0
    assert arts[1]["title"] == "Markets slide - Mint - Livemint"


def test_split_google_title_without_source_element():
    assert tools._split_google_title("Budget 2026 explained - The Hindu", "") == ("Budget 2026 explained", "The Hindu")
    assert tools._split_google_title("No suffix here", "") == ("No suffix here", "")


def test_parse_feed_caps_entries():
    items = [(f"Item {i}", f"https://x/{i}", NOW) for i in range(80)]
    assert len(tools._parse_feed_sync(_rss(items), "S")) == tools._NEWS_MAX_ENTRIES


async def test_google_fallback_used_when_feeds_sparse(monkeypatch, memory_cache):
    seen = []

    def handler(request: httpx.Request):
        seen.append(str(request.url))
        if request.url.host == "news.google.com":
            assert request.url.params["q"] == "rbi interest rate"
            assert request.url.params["gl"] == "IN"
            return httpx.Response(200, text=_rss(
                [("RBI keeps interest rate unchanged - Reuters", "https://news.google.com/r1", NOW)],
                source="Reuters",
            ))
        if "ndtv" in request.url.host or "feedburner" in request.url.host:
            return httpx.Response(200, text=_rss([("RBI | rate decision", "https://ndtv/1", NOW)]))
        return httpx.Response(200, text=_rss([]))

    _mock_async_client(monkeypatch, handler)
    out = await tools.latest_news.ainvoke({"topic": "Latest news about RBI interest rate"})
    news = [line.split("|") for line in out.splitlines() if line.startswith("NEWS|")]
    assert news[0][1] == "RBI keeps interest rate unchanged"
    assert news[0][2] == "Reuters"
    assert news[0][4] == "https://news.google.com/r1"
    assert news[1][1] == "RBI / rate decision"
    assert all(len(n) == 5 for n in news)
    assert any("news.google.com" in u for u in seen)
    assert len(memory_cache) == 1


async def test_google_fallback_skipped_when_feeds_rich(monkeypatch, memory_cache):
    hosts = []

    def handler(request: httpx.Request):
        hosts.append(request.url.host)
        items = [(f"GST council update {i}", f"https://{request.url.host}/{i}", NOW) for i in range(3)]
        return httpx.Response(200, text=_rss(items))

    _mock_async_client(monkeypatch, handler)
    out = await tools._news("GST")
    assert out.ok and out.provider == "rss"
    assert "news.google.com" not in hosts


async def test_no_news_returns_empty_with_web_search_hint_and_not_cached(monkeypatch, memory_cache):
    _mock_async_client(monkeypatch, lambda r: httpx.Response(200, text=_rss([("Unrelated", "https://u/1", NOW)])))
    out = await tools.latest_news.ainvoke({"topic": "xyzzy nonsense topic"})
    assert out.startswith("No recent news found for 'xyzzy nonsense topic'")
    assert "web_search" in out
    assert "Do not call latest_news again" in out
    assert memory_cache == {}


async def test_all_feeds_failing_is_empty_not_cached(monkeypatch, memory_cache):
    _mock_async_client(monkeypatch, lambda r: httpx.Response(503))
    out = await tools._news("RBI")
    assert out.status == "empty"
    assert "web_search" in out.text


async def test_filler_only_topic_returns_top_headlines(monkeypatch, memory_cache):
    hosts = []
    older = NOW - timedelta(hours=2)

    def handler(request: httpx.Request):
        hosts.append(request.url.host)
        if "thehindu" in request.url.host:
            return httpx.Response(200, text=_rss([(f"Hindu {i}", f"https://h/{i}", NOW) for i in range(15)]))
        return httpx.Response(200, text=_rss([(f"Other {request.url.host}", f"https://{request.url.host}/1", older)]))

    _mock_async_client(monkeypatch, handler)
    out = await tools.latest_news.ainvoke({"topic": "latest news today"})
    assert out.startswith("Top headlines")
    lines = [line for line in out.splitlines() if line.startswith("NEWS|")]
    assert len(lines) == tools._NEWS_MAX_RESULTS
    assert sum(1 for line in lines if line.startswith("NEWS|Other")) >= 2
    assert "news.google.com" not in hosts
    assert list(memory_cache) == [f"research:news:{tools._hash('__top__')}"]


async def test_news_cache_key_ignores_filler(monkeypatch, memory_cache):
    calls = []

    async def fake_news(topic):
        calls.append(topic)
        return tools._ok("Found 1\nNEWS|t|s|p|u")

    monkeypatch.setattr(tools, "_news", fake_news)
    await tools.latest_news.ainvoke({"topic": "Latest cricket news"})
    await tools.latest_news.ainvoke({"topic": "cricket news today"})
    assert calls == ["Latest cricket news"]


def _chart(price=100.0, closes=(98.0, 99.0, 100.0), pct=None, currency="USD", name="Acme Inc."):
    meta = {
        "regularMarketPrice": price, "currency": currency, "longName": name,
        "fiftyTwoWeekHigh": 120.0, "fiftyTwoWeekLow": 80.0, "chartPreviousClose": 50.0,
    }
    if pct is not None:
        meta["regularMarketChangePercent"] = pct
    return {"chart": {"result": [{"meta": meta, "indicators": {"quote": [{"close": list(closes)}]}}], "error": None}}


def test_chart_to_info_uses_previous_session_close_not_chart_previous_close():
    info = tools.chart_to_info(_chart(closes=(90.0, None, 99.0, 100.0)))
    assert info["previousClose"] == 99.0
    assert "changePercent" not in info
    assert tools.chart_to_info({"chart": {"result": None, "error": {"code": "Not Found"}}}) == {}
    assert tools.chart_to_info(_chart(price=None)) == {}


def test_stock_output_format_and_change_precedence():
    info = tools.chart_to_info(_chart(pct=-0.8781))
    structured, readable = tools._build_stock_result("AAPL", info)
    assert structured == "STOCK|AAPL|100.0|-0.88%||120.0|80.0"
    assert "Acme Inc. (AAPL)" in readable and "USD 100.0" in readable and "P/E" not in readable
    structured, readable = tools._build_stock_result("AAPL", {**tools.chart_to_info(_chart()), "trailingPE": 31.456})
    assert structured == "STOCK|AAPL|100.0|+1.01%|31.46|120.0|80.0"
    assert "P/E Ratio: 31.46" in readable


def test_block_formatter_tolerates_empty_pe():
    out = "STOCK|^NSEI|22421.95|-0.88%||26373.2|22182.55\nNIFTY 50 (^NSEI)"
    card = _parse_financial_card(ToolResult(tool_name="get_stock_price", output=out))
    assert card is not None
    assert "P/E" not in card.body
    assert "Change: -0.88%" in card.body
    assert "52w:" in card.body


async def test_yahoo_chart_404_is_not_found_and_429_falls_back_to_query2(monkeypatch):
    calls = []

    def handler(request: httpx.Request):
        calls.append((request.url.host, request.url.raw_path.decode()))
        assert request.headers["user-agent"].startswith("Mozilla/5.0")
        if "ZZZ" in request.url.raw_path.decode():
            return httpx.Response(404, json={"chart": {"result": None}})
        if request.url.host.startswith("query1"):
            return httpx.Response(429, text="Too Many Requests")
        return httpx.Response(200, json=_chart(currency="INR"))

    _mock_async_client(monkeypatch, handler)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    out = await tools._stock("Nifty 50", ["^NSEI"])
    assert out.ok and out.text.startswith("STOCK|^NSEI|100.0|+1.01%|")
    assert calls[0][1].startswith("/v8/finance/chart/%5ENSEI")
    assert [h for h, _ in calls] == ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    nf = await tools._stock("ZZZ", ["ZZZ"])
    assert nf.status == "empty"


async def test_candidates_resolved_concurrently_first_valid_in_order(monkeypatch):
    started = {}

    async def chart(client, sym):
        started[sym] = time.perf_counter()
        await asyncio.sleep(0.3 if sym == "ABC" else 0.05)
        return {"regularMarketPrice": 10.0 if sym == "ABC" else 20.0, "previousClose": 10.0, "currency": "INR"}

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    t0 = time.perf_counter()
    out = await tools._stock("ABC", ["ABC", "ABC.NS"])
    assert time.perf_counter() - t0 < 0.55
    assert abs(started["ABC"] - started["ABC.NS"]) < 0.05
    assert out.text.startswith("STOCK|ABC|10.0|")


async def test_failing_candidate_does_not_fail_other(monkeypatch):
    async def chart(client, sym):
        if sym == "RELIANCE":
            raise httpx.ConnectError("boom")
        return {"regularMarketPrice": 1167.7, "previousClose": 1187.0, "currency": "INR", "longName": "Reliance"}

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    out = await tools._stock("RELIANCE", ["RELIANCE", "RELIANCE.NS"])
    assert out.ok
    assert out.text.startswith("STOCK|RELIANCE.NS|1167.7|-1.63%|")
    assert "₹1167.7" in out.text


async def test_all_candidates_erroring_is_error_not_cached(monkeypatch, memory_cache):
    async def chart(client, sym):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    out = await tools.get_stock_price.ainvoke({"symbol": "TCS"})
    assert out.startswith("Could not fetch stock data for TCS: ReadTimeout")
    assert memory_cache == {}


async def test_stock_deadline_returns_error_quickly(monkeypatch, memory_cache):
    async def chart(client, sym):
        await asyncio.sleep(30)

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {})
    monkeypatch.setattr(tools, "_STOCK_DEADLINE_S", 0.2)
    t0 = time.perf_counter()
    out = await tools.get_stock_price.ainvoke({"symbol": "AAPL"})
    assert time.perf_counter() - t0 < 1.5
    assert "timed out" in out
    assert memory_cache == {}


async def test_stock_success_cached(monkeypatch, memory_cache):
    async def chart(client, sym):
        return {"regularMarketPrice": 5.0, "previousClose": 4.0, "currency": "USD"}

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", lambda s: {"trailingPE": 12.0})
    out = await tools.get_stock_price.ainvoke({"symbol": "aapl.us"})
    assert out.startswith("STOCK|AAPL.US|5.0|+25.00%|12.0|")
    assert memory_cache == {"research:stock:AAPL.US": out}


async def test_slow_pe_does_not_block_price(monkeypatch):
    async def chart(client, sym):
        return {"regularMarketPrice": 5.0, "previousClose": 5.0, "currency": "USD"}

    def slow_info(sym):
        time.sleep(0.6)
        return {"trailingPE": 99.0}

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", slow_info)
    monkeypatch.setattr(tools, "_PE_BUDGET_S", 0.1)
    t0 = time.perf_counter()
    out = await tools._stock("MSFT", ["MSFT"])
    assert time.perf_counter() - t0 < 0.4
    assert out.text.startswith("STOCK|MSFT|5.0|+0.00%||")


async def test_pe_lookup_failure_ignored_and_skipped_for_indices(monkeypatch):
    looked = []

    async def chart(client, sym):
        return {"regularMarketPrice": 5.0, "previousClose": 5.0, "currency": "INR"}

    def info(sym):
        looked.append(sym)
        raise RuntimeError("crumb")

    monkeypatch.setattr(tools, "_yahoo_chart", chart)
    monkeypatch.setattr(tools, "_yf_info_sync", info)
    out = await tools._stock("TCS", ["TCS.NS"])
    assert out.ok and out.text.startswith("STOCK|TCS.NS|5.0|+0.00%||")
    await tools._stock("Nifty", ["^NSEI"])
    assert looked == ["TCS.NS"]


def test_user_agent_renamed():
    assert tools._USER_AGENT == "LumenResearchAgent/1.0"
