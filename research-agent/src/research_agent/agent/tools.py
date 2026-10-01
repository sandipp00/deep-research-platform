from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

import httpx
from langchain_core.tools import tool

from research_agent.agent import safe_http
from research_agent.config import get_settings
from research_agent.infrastructure.redis_client import cache_get, cache_set
from research_agent.metrics import ToolRecord, record_tool

logger = logging.getLogger(__name__)
settings = get_settings()

_USER_AGENT = "AlvoffResearchAgent/1.0"

Status = Literal["ok", "empty", "error"]


@dataclass(frozen=True)
class ToolOutput:
    text: str
    status: Status = "ok"
    provider: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _ok(text: str, provider: str | None = None) -> ToolOutput:
    return ToolOutput(text, "ok", provider)


def _empty(text: str, provider: str | None = None) -> ToolOutput:
    return ToolOutput(text, "empty", provider)


def _error(text: str, provider: str | None = None) -> ToolOutput:
    return ToolOutput(text, "error", provider)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _field(value: object) -> str:
    return re.sub(r"\s+", " ", str(value).replace("|", "/")).strip()


def _short_err(e: BaseException) -> str:
    msg = str(e).strip()
    return f"{type(e).__name__}: {msg[:200]}" if msg else type(e).__name__


async def _cached(
    tool_name: str,
    key: str,
    ttl: int,
    fetch: Callable[[], Awaitable[ToolOutput]],
) -> str:
    started = time.perf_counter()
    cached = await cache_get(key)
    if cached:
        record_tool(ToolRecord(tool_name, _ms(started), True, True, "cache"))
        return cached
    try:
        out = await fetch()
    except Exception as e:
        logger.warning("%s raised: %r", tool_name, e)
        out = _error(f"{tool_name} failed: {_short_err(e)}")
    if out.ok and out.text.strip():
        await cache_set(key, out.text, ttl)
    record_tool(ToolRecord(tool_name, _ms(started), False, out.ok, out.provider))
    return out.text


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _format_results(items: list[dict], title_key: str, body_key: str, url_key: str) -> list[str]:
    lines = []
    for i, r in enumerate(items, 1):
        body = (r.get(body_key) or "")[:300].strip()
        lines.append(f"{i}. **{r.get(title_key, '')}**\n   {body}\n   Source: {r.get(url_key, '')}")
    return lines


def _octen_search_sync(query: str) -> list[dict]:
    from octen import Octen

    with Octen(api_key=settings.OCTEN_API_KEY) as octen:
        response = octen.search.search(
            query=query,
            count=settings.OCTEN_MAX_RESULTS,
            highlight={"enable": True, "max_tokens": 300},
        )
    return list(response.results or [])


async def _tavily_search(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "search_depth": settings.TAVILY_SEARCH_DEPTH,
                "max_results": settings.TAVILY_MAX_RESULTS,
            },
        )
        resp.raise_for_status()
        return list(resp.json().get("results") or [])


def _ddg_search_sync(query: str) -> list[dict]:
    from duckduckgo_search import DDGS

    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=5))


async def _search(query: str) -> ToolOutput:
    if settings.OCTEN_API_KEY:
        try:
            results = await asyncio.to_thread(_octen_search_sync, query)
            if results:
                return _ok("\n\n".join(_format_results(results, "title", "highlight", "url")), "octen")
            logger.info("Octen returned no results, trying next provider")
        except Exception as e:
            logger.warning("Octen failed, trying next provider: %r", e)

    if settings.TAVILY_API_KEY:
        try:
            results = await _tavily_search(query)
            if results:
                return _ok("\n\n".join(_format_results(results, "title", "content", "url")), "tavily")
            logger.info("Tavily returned no results, trying DuckDuckGo")
        except Exception as e:
            logger.warning("Tavily failed, trying DuckDuckGo: %r", e)

    try:
        results = await asyncio.to_thread(_ddg_search_sync, query)
    except Exception as e:
        logger.error("All search providers failed: %r", e)
        return _error(f"Search failed: {_short_err(e)}", "duckduckgo")
    if not results:
        return _empty("No results found.", "duckduckgo")
    return _ok("\n\n".join(_format_results(results, "title", "body", "href")), "duckduckgo")


_WEB_SEARCH_DESCRIPTION = (
    'Search the web for current information. Use for general research, news, competitor\n'
    'analysis, product comparisons, government policy, local search with explicit city.\n'
    'Returns numbered results with titles, snippets, and source URLs.'
)


@tool(description=_WEB_SEARCH_DESCRIPTION)
async def web_search(query: str) -> str:
    return await _cached("web_search", f"research:search:{_hash(query)}", 3600, lambda: _search(query))


def _pdf_to_text_sync(data: bytes) -> str:
    import fitz

    with fitz.open(stream=data, filetype="pdf") as doc:
        parts = []
        total = 0
        for page in doc:
            text = page.get_text()
            parts.append(text)
            total += len(text)
            if total > 8000:
                break
    return "\n".join(parts)


async def _read_page(url: str) -> ToolOutput:
    try:
        await safe_http.validate_url(url)
    except safe_http.BlockedURLError as e:
        return _error(f"Blocked URL: {e}. Only public http(s) URLs can be read.")

    max_bytes = settings.WEBPAGE_MAX_BYTES
    headers = {"Accept": "text/plain", "User-Agent": _USER_AGENT}
    if settings.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"
    try:
        res = await safe_http.safe_get(
            f"https://r.jina.ai/{url}", max_bytes=max_bytes, headers=headers,
            timeout=httpx.Timeout(30.0, connect=8.0),
        )
        if res.status_code == 200 and len(res.text) > 200:
            return _ok(res.text[:8000], "jina")
    except Exception as e:
        logger.warning("Jina failed for %s: %r", url, e)

    if "pdf" in url.lower():
        try:
            res = await safe_http.safe_get(url, max_bytes=max_bytes, headers={"User-Agent": _USER_AGENT})
            if res.status_code != 200:
                return _error(f"Could not read content from {url}: HTTP {res.status_code}.")
            text = await asyncio.to_thread(_pdf_to_text_sync, res.content)
            if text.strip():
                return _ok(text[:8000], "pymupdf")
        except safe_http.BlockedURLError as e:
            return _error(f"Blocked URL: {e}. Only public http(s) URLs can be read.")
        except safe_http.ResponseTooLargeError:
            return _error(f"Could not read content from {url}: document exceeds {max_bytes} bytes.")
        except Exception as e:
            logger.warning("PyMuPDF failed for %s: %r", url, e)

    return _error(f"Could not read content from {url}. The page may require authentication or JavaScript.")


_READ_WEBPAGE_DESCRIPTION = (
    'Read the full content of a webpage or PDF as clean text. Use when you need\n'
    'the full article content, government PDFs (RBI/SEBI/Ministry docs), annual reports.\n'
    'Handles PDFs automatically.'
)


@tool(description=_READ_WEBPAGE_DESCRIPTION)
async def read_webpage(url: str) -> str:
    return await _cached("read_webpage", f"research:page:{_hash(url)}", 21600, lambda: _read_page(url))


def _wiki_lookup_sync(query: str) -> str | None:
    import wikipediaapi

    wiki = wikipediaapi.Wikipedia(language="en", user_agent=_USER_AGENT)
    page = wiki.page(query)
    if page.exists():
        return page.summary[:1500]
    results = wiki.search(query, limit=3)
    for title in list(results.pages.keys())[:1]:
        page = wiki.page(title)
        if page.exists():
            return page.summary[:1500]
    return None


async def _wiki(query: str) -> ToolOutput:
    try:
        summary = await asyncio.to_thread(_wiki_lookup_sync, query)
    except Exception as e:
        logger.warning("Wikipedia search failed: %r", e)
        return _error(f"Wikipedia lookup failed: {_short_err(e)}")
    if not summary or not summary.strip():
        return _empty(f"No Wikipedia article found for '{query}'.")
    return _ok(summary)


_WIKI_SEARCH_DESCRIPTION = (
    'Search Wikipedia for factual information. Use for definitions, overviews,\n'
    'historical facts, general knowledge about companies, people, places, or concepts.'
)


@tool(description=_WIKI_SEARCH_DESCRIPTION)
async def wiki_search(query: str) -> str:
    return await _cached("wiki_search", f"research:wiki:{_hash(query)}", 86400, lambda: _wiki(query))


_OSM_TAGS: dict[str, tuple[str, str]] = {
    "charging_station": ("amenity", "charging_station"),
    "ev_charging": ("amenity", "charging_station"),
    "fuel": ("amenity", "fuel"),
    "petrol": ("amenity", "fuel"),
    "gas_station": ("amenity", "fuel"),
    "hospital": ("amenity", "hospital"),
    "atm": ("amenity", "atm"),
    "pharmacy": ("amenity", "pharmacy"),
    "restaurant": ("amenity", "restaurant"),
    "cafe": ("amenity", "cafe"),
    "bank": ("amenity", "bank"),
    "school": ("amenity", "school"),
    "police": ("amenity", "police"),
    "post_office": ("amenity", "post_office"),
}

_PLACE_TYPE_RE = re.compile(r"^[a-z0-9_]{1,40}$")

_OVERPASS_DEADLINE_S = 35

_OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]


def osm_tag_for(place_type: str) -> tuple[str, str] | None:
    key = re.sub(r"[\s\-]+", "_", place_type.strip().lower())
    if key in _OSM_TAGS:
        return _OSM_TAGS[key]
    if _PLACE_TYPE_RE.fullmatch(key):
        return ("amenity", key)
    return None


async def _nearby(place: str, place_type: str, radius_meters: int) -> ToolOutput:
    tag = osm_tag_for(place_type)
    if tag is None:
        return _error(f"Unsupported place type '{_field(place_type)[:40]}'. Use a simple type like fuel, hospital, atm.")
    tag_key, tag_val = tag
    try:
        radius = max(100, min(int(radius_meters), 20000))
    except (TypeError, ValueError):
        radius = 3000

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            geo_resp = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": place, "format": "json", "limit": 1},
                headers={"User-Agent": _USER_AGENT},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
    except Exception as e:
        return _error(f"Could not geocode '{place}': {_short_err(e)}")

    if not geo_data:
        return _empty(f"Location not found: {place}")

    lat = float(geo_data[0]["lat"])
    lon = float(geo_data[0]["lon"])

    overpass_query = f"""
[out:json][timeout:10];
(
  node["{tag_key}"="{tag_val}"](around:{radius},{lat},{lon});
  way["{tag_key}"="{tag_val}"](around:{radius},{lat},{lon});
);
out body center 15;
"""
    osm_data = None
    last_err: Exception | None = None
    try:
        async with asyncio.timeout(_OVERPASS_DEADLINE_S):
            for attempt in range(2):
                for url in _OVERPASS_MIRRORS:
                    try:
                        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5)) as client:
                            osm_resp = await client.post(
                                url,
                                data={"data": overpass_query},
                                headers={"User-Agent": _USER_AGENT},
                            )
                            osm_resp.raise_for_status()
                            osm_data = osm_resp.json()
                        break
                    except Exception as e:
                        last_err = e
                        logger.warning("Overpass %s failed: %r", url, e)
                if osm_data is not None:
                    break
                await asyncio.sleep(1.5 * (attempt + 1))
    except TimeoutError:
        last_err = last_err or TimeoutError(f"no response within {_OVERPASS_DEADLINE_S}s")
    if osm_data is None:
        return _error(f"Overpass API unavailable on all mirrors: {_short_err(last_err) if last_err else 'unknown'}")

    elements = osm_data.get("elements", [])
    label = tag_val.replace("_", " ")
    if not elements:
        return _empty(f"No {label} found within {radius}m of {place}.")

    lines = [f"Found {len(elements)} {label} location(s) near {_field(place)}:\n"]
    for el in elements[:15]:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("brand") or label.title()
        if el.get("type") == "node":
            elat, elon = el.get("lat", lat), el.get("lon", lon)
        else:
            center = el.get("center", {})
            elat, elon = center.get("lat", lat), center.get("lon", lon)
        addr_parts = [tags.get("addr:housenumber", ""), tags.get("addr:street", ""), tags.get("addr:city", "")]
        address = ", ".join(p for p in addr_parts if p) or place
        dist_km = math.sqrt((elat - lat) ** 2 + (elon - lon) ** 2) * 111
        lines.append(f"PLACE|{_field(name)}|{elat}|{elon}|{_field(address)}|{dist_km:.1f}km")
    return _ok("\n".join(lines))


_NEARBY_PLACES_DESCRIPTION = (
    'Find nearby places of a given type around a location using OpenStreetMap.\n'
    'Use for precise radius queries: fuel stations, EV chargers, hospitals, ATMs, pharmacies.\n'
    'Returns structured PLACE|name|lat|lon|address lines for map rendering.\n'
    '\n'
    'Args:\n'
    '    place: City or area name (e.g., "Koramangala, Bangalore")\n'
    '    place_type: Type of place (fuel, charging_station, hospital, atm, pharmacy, restaurant)\n'
    '    radius_meters: Search radius in meters (default: 3000)'
)


@tool(description=_NEARBY_PLACES_DESCRIPTION)
async def nearby_places(place: str, place_type: str, radius_meters: int = 3000) -> str:
    key = f"research:osm:{_hash(place + '|' + place_type + '|' + str(radius_meters))}"
    return await _cached("nearby_places", key, 86400, lambda: _nearby(place, place_type, radius_meters))


_RSS_FEEDS = [
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
    ("Economic Times", "https://economictimes.indiatimes.com/rssfeedstopstories.cms"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
]


def _parse_feed_sync(text: str) -> list[dict]:
    import feedparser

    return list(feedparser.parse(text).entries[:20])


async def _fetch_feed(client: httpx.AsyncClient, source: str, url: str, keywords: list[str]) -> list[str]:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        entries = await asyncio.to_thread(_parse_feed_sync, resp.text)
    except Exception as e:
        logger.warning("RSS feed %s failed: %r", source, e)
        return []
    out = []
    for entry in entries:
        title = entry.get("title", "")
        summary = entry.get("summary", "")
        if any(kw in f"{title} {summary}".lower() for kw in keywords):
            out.append(
                f"NEWS|{_field(title)}|{_field(source)}|{_field(entry.get('published', ''))}|{_field(entry.get('link', ''))}"
            )
    return out


async def _news(topic: str) -> ToolOutput:
    keywords = topic.lower().split()
    if not keywords:
        return _empty("No topic given.")
    async with httpx.AsyncClient(
        timeout=10, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
    ) as client:
        results = await asyncio.gather(*[_fetch_feed(client, n, u, keywords) for n, u in _RSS_FEEDS])
    matched = [item for sub in results for item in sub]
    if not matched:
        return _empty(f"No recent news found for '{topic}' in Indian news sources.")
    return _ok(f"Found {len(matched)} recent articles about '{topic}':\n" + "\n".join(matched[:10]))


_LATEST_NEWS_DESCRIPTION = (
    'Get the latest news on a topic from Indian news sources (NDTV, Economic Times,\n'
    'Moneycontrol, Times of India). Best for breaking news <1 hour old.\n'
    'Returns structured NEWS|title|source|published|url lines.\n'
    '\n'
    'Args:\n'
    '    topic: Topic to search for (e.g., "RBI interest rate", "Sensex", "GST")'
)


@tool(description=_LATEST_NEWS_DESCRIPTION)
async def latest_news(topic: str) -> str:
    return await _cached("latest_news", f"research:news:{_hash(topic)}", 900, lambda: _news(topic))


_SYMBOL_MAP = {
    "nifty": "^NSEI",
    "nifty50": "^NSEI",
    "nifty 50": "^NSEI",
    "sensex": "^BSESN",
    "bsesensex": "^BSESN",
}


def _normalize_symbol(symbol: str) -> str:
    lower = symbol.lower().strip()
    if lower in _SYMBOL_MAP:
        return _SYMBOL_MAP[lower]
    return symbol.upper().strip()


def stock_candidates(symbol: str) -> list[str]:
    normalized = _normalize_symbol(symbol)
    explicit = normalized.startswith("^") or "." in normalized or "=" in normalized
    return [normalized] if explicit else [normalized, normalized + ".NS"]


def _build_stock_result(sym: str, info: dict) -> tuple[str, str] | None:
    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if not price:
        return None
    prev_close = info.get("previousClose", 0)
    change = ""
    if prev_close and isinstance(price, (int, float)):
        pct = ((price - prev_close) / prev_close) * 100
        sign = "+" if pct >= 0 else ""
        change = f"{sign}{pct:.2f}%"
    pe = info.get("trailingPE", "")
    week_high = info.get("fiftyTwoWeekHigh", "")
    week_low = info.get("fiftyTwoWeekLow", "")
    name = info.get("longName") or info.get("shortName") or sym
    currency = info.get("currency", "")
    price_prefix = "₹" if currency in ("INR", "") else f"{currency} "
    structured = f"STOCK|{sym}|{price}|{change}|{pe}|{week_high}|{week_low}"
    readable = f"{name} ({sym})\nCurrent Price: {price_prefix}{price}\nChange: {change}\n"
    if pe:
        readable += f"P/E Ratio: {pe}\n"
    if week_high and week_low:
        readable += f"52-Week Range: {price_prefix}{week_low} – {price_prefix}{week_high}\n"
    return structured, readable


def _yf_info_sync(sym: str) -> dict:
    import yfinance as yf

    return dict(yf.Ticker(sym).info or {})


async def _stock(symbol: str, candidates: list[str]) -> ToolOutput:
    try:
        for sym in candidates:
            info = await asyncio.to_thread(_yf_info_sync, sym)
            result = _build_stock_result(sym, info)
            if result:
                structured, readable = result
                return _ok(structured + "\n" + readable, "yfinance")
        return _empty(f"Could not fetch stock data for {symbol}: no price data available")
    except Exception as e:
        logger.warning("yfinance failed for %s: %r", symbol, e)
        return _error(f"Could not fetch stock data for {symbol}: {_short_err(e)}")


_GET_STOCK_PRICE_DESCRIPTION = (
    'Get the current stock price and key metrics for a stock.\n'
    'Use for NSE/BSE stocks, global stocks (TSLA, AAPL), Nifty 50, Sensex.\n'
    'Returns structured STOCK|symbol|price|change|pe|52wk_high|52wk_low line.\n'
    '\n'
    'Args:\n'
    '    symbol: Stock symbol (e.g., "RELIANCE", "TCS", "TSLA", "AAPL", "Nifty 50")'
)


@tool(description=_GET_STOCK_PRICE_DESCRIPTION)
async def get_stock_price(symbol: str) -> str:
    candidates = stock_candidates(symbol)
    key = f"research:stock:{candidates[0]}"
    return await _cached("get_stock_price", key, 900, lambda: _stock(symbol, candidates))


async def _forex(frm: str, to: str) -> ToolOutput:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.frankfurter.dev/v1/latest", params={"from": frm, "to": to})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("Frankfurter API failed: %r", e)
        return _error(f"Could not fetch exchange rate for {frm}/{to}: {_short_err(e)}")
    rate = (data.get("rates") or {}).get(to)
    if rate is None:
        return _empty(f"No exchange rate available for {frm}/{to}.")
    date = data.get("date", "today")
    return _ok(f"FOREX|{frm}|{to}|{rate}|{date}\n1 {frm} = {rate} {to} (as of {date})")


_GET_FOREX_RATE_DESCRIPTION = (
    'Get the current foreign exchange rate between two currencies.\n'
    'Use for USD/EUR/GBP to INR conversions and other currency pairs.\n'
    'Returns structured FOREX|from|to|rate|date line.\n'
    '\n'
    'Args:\n'
    '    from_currency: Source currency code (e.g., "USD", "EUR", "GBP")\n'
    '    to_currency: Target currency code (e.g., "INR", "USD")'
)


@tool(description=_GET_FOREX_RATE_DESCRIPTION)
async def get_forex_rate(from_currency: str, to_currency: str) -> str:
    frm = _field(from_currency.upper().strip())
    to = _field(to_currency.upper().strip())
    return await _cached("get_forex_rate", f"research:forex:{frm}:{to}", 3600, lambda: _forex(frm, to))


_CRYPTO_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "sol": "solana",
    "bnb": "binancecoin",
    "xrp": "ripple",
    "ada": "cardano",
    "doge": "dogecoin",
    "matic": "matic-network",
    "dot": "polkadot",
    "ltc": "litecoin",
}


async def _crypto(coin_id: str, normalized: str) -> ToolOutput:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": normalized, "vs_currencies": "inr,usd", "include_24hr_change": "true"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("CoinGecko failed for %s: %r", normalized, e)
        return _error(f"Could not fetch crypto price for {coin_id}: {_short_err(e)}")
    if normalized not in data:
        return _empty(f"Coin '{coin_id}' not found on CoinGecko.")
    coin_data = data[normalized]
    inr = coin_data.get("inr", "N/A")
    usd = coin_data.get("usd", "N/A")
    change = coin_data.get("usd_24h_change") or 0
    change_str = f"{'+' if change >= 0 else ''}{change:.2f}%"
    inr_fmt = f"₹{inr:,.0f}" if isinstance(inr, (int, float)) else str(inr)
    usd_fmt = f"${usd:,.2f}" if isinstance(usd, (int, float)) else str(usd)
    structured = f"CRYPTO|{_field(normalized)}|{inr}|{usd}|{change_str}"
    readable = f"{normalized.capitalize()}: {inr_fmt} / {usd_fmt} · 24h change: {change_str}"
    return _ok(structured + "\n" + readable)


_GET_CRYPTO_PRICE_DESCRIPTION = (
    'Get the current price of a cryptocurrency in INR and USD.\n'
    'Returns structured CRYPTO|coin|inr|usd|change_24h line.\n'
    '\n'
    'Args:\n'
    '    coin_id: Coin name or symbol (e.g., "bitcoin", "BTC", "ethereum", "ETH")'
)


@tool(description=_GET_CRYPTO_PRICE_DESCRIPTION)
async def get_crypto_price(coin_id: str) -> str:
    normalized = _CRYPTO_ALIASES.get(coin_id.lower().strip(), coin_id.lower().strip())
    return await _cached("get_crypto_price", f"research:crypto:{normalized}", 300, lambda: _crypto(coin_id, normalized))
