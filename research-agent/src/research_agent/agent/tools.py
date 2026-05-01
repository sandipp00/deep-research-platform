"""8 custom research tools with Redis caching and structured output."""
from __future__ import annotations

import asyncio
import hashlib
import logging

import httpx
from langchain_core.tools import tool

from research_agent.config import get_settings
from research_agent.infrastructure.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Cache helper ──────────────────────────────────────────────

def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


async def _cached(key: str, ttl: int, coro_factory) -> str:
    cached = await cache_get(key)
    if cached:
        logger.debug("Cache hit: %s", key)
        return cached
    result = await coro_factory()
    await cache_set(key, result, ttl)
    return result


# ── 1. web_search ─────────────────────────────────────────────

@tool
async def web_search(query: str) -> str:
    """Search the web for current information. Use for general research, news, competitor
    analysis, product comparisons, government policy, local search with explicit city.
    Returns numbered results with titles, snippets, and source URLs."""

    cache_key = f"research:search:{_hash(query)}"

    async def _fetch() -> str:
        # Try Exa first
        if settings.EXA_API_KEY:
            try:
                from exa_py import Exa
                exa = Exa(api_key=settings.EXA_API_KEY)
                results = await asyncio.to_thread(
                    exa.search_and_contents,
                    query,
                    text=True,
                    num_results=settings.EXA_MAX_RESULTS,
                )
                if results.results:
                    lines = []
                    for i, r in enumerate(results.results, 1):
                        text = (r.text or "")[:300].strip()
                        lines.append(f"{i}. **{r.title}**\n   {text}\n   Source: {r.url}")
                    return "\n\n".join(lines)
            except Exception as e:
                logger.warning("Exa failed, trying Tavily: %s", e)

        # Tavily fallback
        if settings.TAVILY_API_KEY:
            try:
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
                    data = resp.json()
                    results = data.get("results", [])
                    lines = []
                    for i, r in enumerate(results, 1):
                        content = (r.get("content") or "")[:300].strip()
                        lines.append(f"{i}. **{r.get('title', '')}**\n   {content}\n   Source: {r.get('url', '')}")
                    return "\n\n".join(lines) if lines else "No results found."
            except Exception as e:
                logger.warning("Tavily failed, trying DuckDuckGo: %s", e)

        # DuckDuckGo last resort
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r.get('title', '')}**\n   {r.get('body', '')[:300]}\n   Source: {r.get('href', '')}")
            return "\n\n".join(lines) if lines else "No results found."
        except Exception as e:
            logger.error("All search providers failed: %s", e)
            return f"Search failed: {e}"

    return await _cached(cache_key, 3600, _fetch)


# ── 2. read_webpage ───────────────────────────────────────────

@tool
async def read_webpage(url: str) -> str:
    """Read the full content of a webpage or PDF as clean text. Use when you need
    the full article content, government PDFs (RBI/SEBI/Ministry docs), annual reports.
    Handles PDFs automatically."""

    cache_key = f"research:page:{_hash(url)}"

    async def _fetch() -> str:
        # Try Jina Reader
        try:
            headers = {"Accept": "text/plain"}
            if settings.JINA_API_KEY:
                headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"https://r.jina.ai/{url}", headers=headers)
                if resp.status_code == 200 and len(resp.text) > 200:
                    return resp.text[:8000]
        except Exception as e:
            logger.warning("Jina failed for %s: %s", url, e)

        # PyMuPDF fallback for PDFs
        if url.lower().endswith(".pdf") or "pdf" in url.lower():
            try:
                import fitz  # pymupdf
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                doc = fitz.open(stream=resp.content, filetype="pdf")
                text = "\n".join(page.get_text() for page in doc)
                return text[:8000]
            except Exception as e:
                logger.warning("PyMuPDF failed for %s: %s", url, e)

        return f"Could not read content from {url}. The page may require authentication or JavaScript."

    return await _cached(cache_key, 21600, _fetch)


# ── 3. wiki_search ────────────────────────────────────────────

@tool
async def wiki_search(query: str) -> str:
    """Search Wikipedia for factual information. Use for definitions, overviews,
    historical facts, general knowledge about companies, people, places, or concepts."""

    cache_key = f"research:wiki:{_hash(query)}"

    async def _fetch() -> str:
        try:
            import wikipediaapi
            wiki = wikipediaapi.Wikipedia(
                language="en",
                user_agent="AlvoffResearchAgent/1.0",
            )
            page = wiki.page(query)
            if page.exists():
                # Return first ~1500 chars of summary
                return page.summary[:1500]

            # Try search if direct page not found
            import wikipedia
            results = wikipedia.search(query, results=3)
            if results:
                page = wiki.page(results[0])
                if page.exists():
                    return page.summary[:1500]

            return f"No Wikipedia article found for '{query}'."
        except Exception as e:
            logger.warning("Wikipedia search failed: %s", e)
            return f"Wikipedia lookup failed: {e}"

    return await _cached(cache_key, 86400, _fetch)


# ── 4. nearby_places ─────────────────────────────────────────

# OSM amenity tag mapping
_OSM_TAGS: dict[str, str] = {
    "charging_station": "amenity=charging_station",
    "ev_charging": "amenity=charging_station",
    "fuel": "amenity=fuel",
    "petrol": "amenity=fuel",
    "gas_station": "amenity=fuel",
    "hospital": "amenity=hospital",
    "atm": "amenity=atm",
    "pharmacy": "amenity=pharmacy",
    "restaurant": "amenity=restaurant",
    "cafe": "amenity=cafe",
    "bank": "amenity=bank",
    "school": "amenity=school",
    "police": "amenity=police",
    "post_office": "amenity=post_office",
}


@tool
async def nearby_places(place: str, place_type: str, radius_meters: int = 3000) -> str:
    """Find nearby places of a given type around a location using OpenStreetMap.
    Use for precise radius queries: fuel stations, EV chargers, hospitals, ATMs, pharmacies.
    Returns structured PLACE|name|lat|lon|address lines for map rendering.

    Args:
        place: City or area name (e.g., "Koramangala, Bangalore")
        place_type: Type of place (fuel, charging_station, hospital, atm, pharmacy, restaurant)
        radius_meters: Search radius in meters (default: 3000)
    """

    cache_key = f"research:osm:{_hash(place + place_type + str(radius_meters))}"

    async def _fetch() -> str:
        # Geocode the place name
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                geo_resp = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": place, "format": "json", "limit": 1},
                    headers={"User-Agent": "AlvoffResearchAgent/1.0"},
                )
                geo_resp.raise_for_status()
                geo_data = geo_resp.json()
        except Exception as e:
            return f"Could not geocode '{place}': {e}"

        if not geo_data:
            return f"Location not found: {place}"

        lat = float(geo_data[0]["lat"])
        lon = float(geo_data[0]["lon"])

        # Build Overpass query
        osm_tag = _OSM_TAGS.get(place_type.lower(), f"amenity={place_type}")
        tag_key, tag_val = osm_tag.split("=", 1)
        overpass_query = f"""
[out:json];
(
  node["{tag_key}"="{tag_val}"](around:{radius_meters},{lat},{lon});
  way["{tag_key}"="{tag_val}"](around:{radius_meters},{lat},{lon});
);
out body center 15;
"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                osm_resp = await client.post(
                    "https://overpass-api.de/api/interpreter",
                    data={"data": overpass_query},
                    headers={"User-Agent": "AlvoffResearchAgent/1.0"},
                )
                osm_resp.raise_for_status()
                osm_data = osm_resp.json()
        except Exception as e:
            return f"Overpass API failed: {e}"

        elements = osm_data.get("elements", [])
        if not elements:
            return f"No {place_type} found within {radius_meters}m of {place}."

        lines = [f"Found {len(elements)} {place_type} location(s) near {place}:\n"]
        for el in elements[:15]:  # cap at 15
            tags = el.get("tags", {})
            name = tags.get("name") or tags.get("brand") or place_type.replace("_", " ").title()

            # Get coordinates (nodes have lat/lon directly; ways have center)
            if el.get("type") == "node":
                elat, elon = el.get("lat", lat), el.get("lon", lon)
            else:
                center = el.get("center", {})
                elat, elon = center.get("lat", lat), center.get("lon", lon)

            # Build address
            addr_parts = [
                tags.get("addr:housenumber", ""),
                tags.get("addr:street", ""),
                tags.get("addr:city", ""),
            ]
            address = ", ".join(p for p in addr_parts if p) or place

            # Approximate distance (simple Euclidean — fine for display)
            import math
            dist_km = math.sqrt((elat - lat) ** 2 + (elon - lon) ** 2) * 111
            dist_str = f"{dist_km:.1f}km"

            lines.append(f"PLACE|{name}|{elat}|{elon}|{address}|{dist_str}")

        return "\n".join(lines)

    return await _cached(cache_key, 86400, _fetch)


# ── 5. latest_news ────────────────────────────────────────────

_RSS_FEEDS = [
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
    ("Economic Times", "https://economictimes.indiatimes.com/rssfeedstopstories.cms"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/MCtopnews.xml"),
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
]


@tool
async def latest_news(topic: str) -> str:
    """Get the latest news on a topic from Indian news sources (NDTV, Economic Times,
    Moneycontrol, Times of India). Best for breaking news <1 hour old.
    Returns structured NEWS|title|source|published|url lines.

    Args:
        topic: Topic to search for (e.g., "RBI interest rate", "Sensex", "GST")
    """

    cache_key = f"research:news:{_hash(topic)}"

    async def _fetch() -> str:
        import feedparser
        keywords = topic.lower().split()

        async def _fetch_one(source_name: str, feed_url: str) -> list[str]:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(feed_url)
                feed = feedparser.parse(resp.text)
                results = []
                for entry in feed.entries[:20]:
                    title = entry.get("title", "")
                    summary = entry.get("summary", "")
                    if any(kw in (title + " " + summary).lower() for kw in keywords):
                        results.append(
                            f"NEWS|{title}|{source_name}|{entry.get('published', '')}|{entry.get('link', '')}"
                        )
                return results
            except Exception as e:
                logger.warning("RSS feed %s failed: %s", source_name, e)
                return []

        feed_results = await asyncio.gather(*[_fetch_one(n, u) for n, u in _RSS_FEEDS])
        matched = [item for sublist in feed_results for item in sublist]

        if not matched:
            return f"No recent news found for '{topic}' in Indian news sources."

        header = f"Found {len(matched)} recent articles about '{topic}':\n"
        return header + "\n".join(matched[:10])

    return await _cached(cache_key, 900, _fetch)


# ── 6. get_stock_price ────────────────────────────────────────

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
    sym = symbol.upper().strip()
    # Preserve explicit exchange suffixes; bare symbols tried as-is first
    # (covers NASDAQ/NYSE), then retried with .NS for Indian NSE stocks.
    return sym


def _build_stock_result(sym: str, info: dict) -> tuple[str, str] | None:
    """Return (structured_line, readable_text) or None if price unavailable."""
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
    readable = (
        f"{name} ({sym})\n"
        f"Current Price: {price_prefix}{price}\n"
        f"Change: {change}\n"
    )
    if pe:
        readable += f"P/E Ratio: {pe}\n"
    if week_high and week_low:
        readable += f"52-Week Range: {price_prefix}{week_low} – {price_prefix}{week_high}\n"
    return structured, readable


@tool
async def get_stock_price(symbol: str) -> str:
    """Get the current stock price and key metrics for a stock.
    Use for NSE/BSE stocks, global stocks (TSLA, AAPL), Nifty 50, Sensex.
    Returns structured STOCK|symbol|price|change|pe|52wk_high|52wk_low line.

    Args:
        symbol: Stock symbol (e.g., "RELIANCE", "TCS", "TSLA", "AAPL", "Nifty 50")
    """

    normalized = _normalize_symbol(symbol)
    # Decide candidate symbols: bare ticker first, then .NS fallback for Indian stocks
    has_suffix = any(normalized.endswith(s) for s in (".NS", ".BO", "^"))
    candidates = [normalized] if has_suffix else [normalized, normalized + ".NS"]
    cache_key = f"research:stock:{normalized}"

    async def _fetch() -> str:
        try:
            import yfinance as yf
            for sym in candidates:
                ticker = yf.Ticker(sym)
                info = ticker.info
                result = _build_stock_result(sym, info)
                if result:
                    structured, readable = result
                    return structured + "\n" + readable
            return f"Could not fetch stock data for {symbol}: no price data available"
        except Exception as e:
            logger.warning("yfinance failed for %s: %s", normalized, e)
            return f"Could not fetch stock data for {symbol}: {e}"

    return await _cached(cache_key, 900, _fetch)


# ── 7. get_forex_rate ─────────────────────────────────────────

@tool
async def get_forex_rate(from_currency: str, to_currency: str) -> str:
    """Get the current foreign exchange rate between two currencies.
    Use for USD/EUR/GBP to INR conversions and other currency pairs.
    Returns structured FOREX|from|to|rate|date line.

    Args:
        from_currency: Source currency code (e.g., "USD", "EUR", "GBP")
        to_currency: Target currency code (e.g., "INR", "USD")
    """

    frm = from_currency.upper().strip()
    to = to_currency.upper().strip()
    cache_key = f"research:forex:{frm}:{to}"

    async def _fetch() -> str:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.frankfurter.dev/v1/latest",
                    params={"from": frm, "to": to},
                )
                resp.raise_for_status()
                data = resp.json()

            rate = data["rates"].get(to, "N/A")
            date = data.get("date", "today")

            structured = f"FOREX|{frm}|{to}|{rate}|{date}"
            readable = f"1 {frm} = {rate} {to} (as of {date})"
            return structured + "\n" + readable
        except Exception as e:
            logger.warning("Frankfurter API failed: %s", e)
            return f"Could not fetch exchange rate for {frm}/{to}: {e}"

    return await _cached(cache_key, 3600, _fetch)


# ── 8. get_crypto_price ───────────────────────────────────────

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


@tool
async def get_crypto_price(coin_id: str) -> str:
    """Get the current price of a cryptocurrency in INR and USD.
    Returns structured CRYPTO|coin|inr|usd|change_24h line.

    Args:
        coin_id: Coin name or symbol (e.g., "bitcoin", "BTC", "ethereum", "ETH")
    """

    normalized = _CRYPTO_ALIASES.get(coin_id.lower(), coin_id.lower())
    cache_key = f"research:crypto:{normalized}"

    async def _fetch() -> str:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.coingecko.com/api/v3/simple/price",
                    params={
                        "ids": normalized,
                        "vs_currencies": "inr,usd",
                        "include_24hr_change": "true",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            if normalized not in data:
                return f"Coin '{coin_id}' not found on CoinGecko."

            coin_data = data[normalized]
            inr = coin_data.get("inr", "N/A")
            usd = coin_data.get("usd", "N/A")
            change = coin_data.get("usd_24h_change", 0)
            sign = "+" if change >= 0 else ""
            change_str = f"{sign}{change:.2f}%"

            # Format INR with commas for readability
            inr_fmt = f"₹{inr:,.0f}" if isinstance(inr, (int, float)) else str(inr)
            usd_fmt = f"${usd:,.2f}" if isinstance(usd, (int, float)) else str(usd)

            structured = f"CRYPTO|{normalized}|{inr}|{usd}|{change_str}"
            readable = f"{normalized.capitalize()}: {inr_fmt} / {usd_fmt} · 24h change: {change_str}"
            return structured + "\n" + readable
        except Exception as e:
            logger.warning("CoinGecko failed for %s: %s", normalized, e)
            return f"Could not fetch crypto price for {coin_id}: {e}"

    return await _cached(cache_key, 300, _fetch)
