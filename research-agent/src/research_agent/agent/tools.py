from __future__ import annotations

import asyncio
import calendar
import hashlib
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

from research_agent.agent import safe_http
from research_agent.config import get_settings
from research_agent.infrastructure.redis_client import cache_get, cache_set
from research_agent.metrics import ToolRecord, record_tool

logger = logging.getLogger(__name__)
settings = get_settings()

_USER_AGENT = "LumenResearchAgent/1.0"

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
    async def _post_overpass(url: str) -> dict:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12, connect=5)) as client:
            osm_resp = await client.post(
                url,
                data={"data": overpass_query},
                headers={"User-Agent": _USER_AGENT},
            )
            osm_resp.raise_for_status()
            return osm_resp.json()

    osm_data = None
    last_err: Exception | None = None
    try:
        async with asyncio.timeout(_OVERPASS_DEADLINE_S):
            for attempt in range(2):
                tasks = {asyncio.create_task(_post_overpass(u)): u for u in _OVERPASS_MIRRORS}
                try:
                    for fut in asyncio.as_completed(list(tasks)):
                        try:
                            osm_data = await fut
                            break
                        except Exception as e:
                            last_err = e
                            logger.warning("Overpass mirror failed: %r", e)
                finally:
                    for t in tasks:
                        t.cancel()
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
    ("Times of India", "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"),
    ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
]

_TOPIC_FEEDS: dict[str, list[tuple[str, str]]] = {
    "cricket": [
        ("ESPNcricinfo", "https://www.espncricinfo.com/rss/content/story/feeds/0.xml"),
        ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/54829575.cms"),
        ("NDTV Sports", "https://feeds.feedburner.com/ndtvsports-cricket"),
        ("The Hindu", "https://www.thehindu.com/sport/cricket/feeder/default.rss"),
    ],
    "sports": [
        ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms"),
        ("NDTV Sports", "https://feeds.feedburner.com/ndtvsports-latest"),
        ("The Hindu", "https://www.thehindu.com/sport/feeder/default.rss"),
    ],
    "tech": [
        ("Economic Times", "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms"),
        ("LiveMint", "https://www.livemint.com/rss/technology"),
        ("The Hindu", "https://www.thehindu.com/sci-tech/technology/feeder/default.rss"),
    ],
    "business": [
        ("Economic Times", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
        ("LiveMint", "https://www.livemint.com/rss/markets"),
        ("The Hindu", "https://www.thehindu.com/business/feeder/default.rss"),
        ("Times of India", "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms"),
    ],
}


def _triggers(categories: tuple[str, ...], credit: bool, words: str) -> dict[str, tuple[tuple[str, ...], bool]]:
    return {w: (categories, credit) for w in words.split()}


_TOPIC_TRIGGERS: dict[str, tuple[tuple[str, ...], bool]] = {
    **_triggers(("cricket",), True, "cricket"),
    **_triggers(("cricket",), False, "ipl wpl bcci icc t20 t20i odi ranji kohli rohit bumrah dhoni gill"),
    **_triggers(("sports", "cricket"), True, "sport sports"),
    **_triggers(
        ("sports",), False,
        "football hockey tennis badminton olympics olympic athletics kabaddi chess fifa isl wrestling boxing "
        "f1 formula golf javelin",
    ),
    **_triggers(("tech",), True, "tech technology"),
    **_triggers(
        ("tech",), False,
        "ai startup startups smartphone smartphones gadgets software semiconductor semiconductors "
        "cybersecurity 5g iphone android chip chips",
    ),
    **_triggers(("business",), True, "business market markets"),
    **_triggers(
        ("business",), False,
        "stock stocks sensex nifty shares ipo rbi economy inflation gdp rupee banking earnings repo fii fiis "
        "sebi bse nse",
    ),
}

_NEWS_STOPWORDS = frozenset(
    """
    a an the and or of in on at to for from by with about into over regarding related around
    is are was were be been being do does did has have had will would can could should
    what whats which who whom whose where when why how any some all this that these those it its
    latest late news new newest recent recently current currently breaking top headline headlines
    update updates updated live today todays tonight yesterday now this week weeks weekly month
    months day days daily past last happening happened going
    me my i we us our you your give show tell get find fetch search look please let know want need
    story stories article articles report reports info information coverage developments situation
    """.split()
)

_NEWS_WEAK_KEYWORDS = frozenset({"india", "indian", "indias", "national", "world", "global", "country"})

_NEWS_MAX_ENTRIES = 50
_NEWS_MAX_RESULTS = 10
_NEWS_MIN_FULL_MATCHES = 3
_NEWS_MAX_AGE_S = 30 * 86400
_NEWS_TIMEOUT = httpx.Timeout(6.0, connect=4.0)
_GOOGLE_NEWS_URL = "https://news.google.com/rss/search"


def news_keywords(topic: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:[&+.][a-z0-9]+)*", topic.lower())
    out: list[str] = []
    for tok in tokens:
        if tok in _NEWS_STOPWORDS or (len(tok) < 2 and not tok.isdigit()) or tok in out:
            continue
        out.append(tok)
    return out


def _keyword_pattern(kw: str) -> re.Pattern:
    base = kw[:-1] if len(kw) > 3 and kw.endswith("s") and not kw.endswith("ss") else kw
    return re.compile(rf"(?<![a-z0-9]){re.escape(base)}(?:s|es|n|ns|'s|’s)?(?![a-z0-9])", re.IGNORECASE)


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _entry_ts(entry: dict) -> float:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return 0.0
    try:
        return float(calendar.timegm(parsed))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _split_google_title(title: str, source: str) -> tuple[str, str]:
    if source and title.endswith(f" - {source}"):
        return title[: -len(f" - {source}")].strip(), source
    if not source and " - " in title:
        head, tail = title.rsplit(" - ", 1)
        if head.strip() and 0 < len(tail.strip()) <= 60:
            return head.strip(), tail.strip()
    return title.strip(), source


def _parse_feed_sync(text: str, source: str, google: bool = False) -> list[dict]:
    import feedparser

    articles = []
    for entry in feedparser.parse(text).entries[:_NEWS_MAX_ENTRIES]:
        title = _strip_html(entry.get("title", ""))
        if not title:
            continue
        src = source
        summary = ""
        if google:
            src_info = entry.get("source") or {}
            title, src = _split_google_title(title, _strip_html(src_info.get("title", "")) if src_info else "")
            src = src or source
        else:
            summary = _strip_html(entry.get("summary", ""))[:600]
        articles.append({
            "title": title,
            "summary": summary,
            "source": src,
            "published": entry.get("published", "") or entry.get("updated", ""),
            "ts": _entry_ts(entry),
            "link": entry.get("link", ""),
            "google": google,
        })
    return articles


async def _fetch_feed(
    client: httpx.AsyncClient, source: str, url: str, params: dict | None = None, google: bool = False
) -> list[dict]:
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return await asyncio.to_thread(_parse_feed_sync, resp.text, source, google)
    except Exception as e:
        logger.warning("RSS feed %s failed: %r", source, e)
        return []


async def _fetch_google_news(client: httpx.AsyncClient, query: str) -> list[dict]:
    params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    return await _fetch_feed(client, "Google News", _GOOGLE_NEWS_URL, params=params, google=True)


def _feeds_for(keywords: list[str]) -> list[tuple[str, str, frozenset[str]]]:
    credits: dict[str, set[str]] = {}
    order: list[str] = []
    for kw in keywords:
        if kw not in _TOPIC_TRIGGERS:
            continue
        categories, credit = _TOPIC_TRIGGERS[kw]
        for cat in categories:
            if cat not in order:
                order.append(cat)
            if credit:
                credits.setdefault(cat, set()).add(kw)
    feeds: dict[str, tuple[str, str, set[str]]] = {u: (n, u, set()) for n, u in _RSS_FEEDS}
    for cat in order:
        for name, url in _TOPIC_FEEDS[cat]:
            feeds.setdefault(url, (name, url, set()))[2].update(credits.get(cat, set()))
    return [(n, u, frozenset(c)) for n, u, c in feeds.values()]


def _score(article: dict, patterns: dict[str, re.Pattern], credited: frozenset[str]) -> tuple[set[str], set[str]]:
    text = article["title"] if article.get("google") else f"{article['title']} {article['summary']}"
    matched = {kw for kw, pat in patterns.items() if pat.search(text)} | set(credited)
    strong = {kw for kw in matched if kw not in _NEWS_WEAK_KEYWORDS}
    return strong, matched - strong


def rank_articles(keywords: list[str], batches: list[tuple[list[dict], frozenset[str]]], now: float) -> tuple[list[dict], int]:
    patterns = {kw: _keyword_pattern(kw) for kw in keywords}
    strong_all = [kw for kw in keywords if kw not in _NEWS_WEAK_KEYWORDS] or list(keywords)
    weak_mode = not [kw for kw in keywords if kw not in _NEWS_WEAK_KEYWORDS]
    need = max(1, math.ceil(len(strong_all) / 2))
    scored = []
    for articles, credited in batches:
        for a in articles:
            if a["ts"] and now - a["ts"] > _NEWS_MAX_AGE_S:
                continue
            strong, weak = _score(a, patterns, credited)
            if weak_mode:
                strong, weak = strong | weak, set()
            hits = len(strong)
            if hits < (1 if a.get("google") else need):
                continue
            full = hits == len(strong_all)
            scored.append(((-hits, -len(weak), -a["ts"]), full, a))
    scored.sort(key=lambda s: s[0])
    seen: set[str] = set()
    ranked, full_count = [], 0
    for _, full, a in scored:
        key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:80]
        if key in seen:
            continue
        seen.add(key)
        ranked.append(a)
        full_count += int(full)
    return ranked, full_count


def _news_line(a: dict) -> str:
    return f"NEWS|{_field(a['title'])}|{_field(a['source'])}|{_field(a['published'])}|{_field(a['link'])}"


def _no_news(topic: str) -> ToolOutput:
    return _empty(
        f"No recent news found for '{topic}' in Indian news feeds or Google News. "
        "Do not call latest_news again with a rephrased topic; use web_search for this topic instead."
    )


async def _top_headlines(client: httpx.AsyncClient, now: float) -> ToolOutput:
    results = await asyncio.gather(*[_fetch_feed(client, n, u) for n, u in _RSS_FEEDS])
    queues = [
        sorted((a for a in sub if not a["ts"] or now - a["ts"] <= _NEWS_MAX_AGE_S), key=lambda a: -a["ts"])
        for sub in results
    ]
    seen: set[str] = set()
    picked = []
    for rnd in range(max((len(q) for q in queues), default=0)):
        batch = sorted((q[rnd] for q in queues if rnd < len(q)), key=lambda a: -a["ts"])
        for a in batch:
            key = re.sub(r"[^a-z0-9]", "", a["title"].lower())[:80]
            if key not in seen:
                seen.add(key)
                picked.append(a)
        if len(picked) >= _NEWS_MAX_RESULTS:
            break
    if not picked:
        return _empty(
            "Could not load top headlines from Indian news feeds right now. Use web_search instead of retrying."
        )
    lines = [_news_line(a) for a in picked[:_NEWS_MAX_RESULTS]]
    return _ok("Top headlines from Indian news sources:\n" + "\n".join(lines), "rss")


async def _news(topic: str) -> ToolOutput:
    keywords = news_keywords(topic)
    now = time.time()
    async with httpx.AsyncClient(
        timeout=_NEWS_TIMEOUT, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
    ) as client:
        if not keywords:
            return await _top_headlines(client, now)
        feeds = _feeds_for(keywords)
        results = await asyncio.gather(*[_fetch_feed(client, n, u) for n, u, _ in feeds])
        batches = [(articles, credited) for articles, (_, _, credited) in zip(results, feeds)]
        ranked, full_count = rank_articles(keywords, batches, now)
        provider = "rss"
        if full_count < _NEWS_MIN_FULL_MATCHES:
            google = await _fetch_google_news(client, " ".join(keywords))
            if google:
                batches.append((google, frozenset()))
                ranked, full_count = rank_articles(keywords, batches, now)
                provider = "rss+google_news"
    if not ranked:
        return _no_news(topic)
    top = ranked[:_NEWS_MAX_RESULTS]
    if full_count:
        header = f"Found {len(top)} recent articles about '{topic}':"
    else:
        header = f"No article matched every keyword of '{topic}'; showing the {len(top)} closest matches:"
    return _ok(header + "\n" + "\n".join(_news_line(a) for a in top), provider)


_LATEST_NEWS_DESCRIPTION = (
    'Get the latest news on a topic from Indian news sources (NDTV, Economic Times, Times of India,\n'
    'The Hindu, LiveMint, ESPNcricinfo) with a Google News fallback. Best for breaking and recent news.\n'
    'Pass a short topic such as "RBI interest rate", "Sensex", "cricket" or "GST"; filler words like\n'
    '"latest" or "news" are ignored, and an empty topic returns top headlines.\n'
    'Call it once per topic: if it reports no news, use web_search instead of retrying with variants.\n'
    'Returns structured NEWS|title|source|published|url lines.\n'
    '\n'
    'Args:\n'
    '    topic: Topic to search for (e.g., "RBI interest rate", "Sensex", "GST")'
)


@tool(description=_LATEST_NEWS_DESCRIPTION)
async def latest_news(topic: str) -> str:
    key = f"research:news:{_hash(' '.join(sorted(news_keywords(topic))) or '__top__')}"
    return await _cached("latest_news", key, 900, lambda: _news(topic))


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


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def _build_stock_result(sym: str, info: dict) -> tuple[str, str] | None:
    price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
    if not price:
        return None
    prev_close = info.get("previousClose", 0)
    change = ""
    pct = _num(info.get("changePercent"))
    if pct is None and prev_close and isinstance(price, (int, float)):
        pct = ((price - prev_close) / prev_close) * 100
    if pct is not None:
        sign = "+" if pct >= 0 else ""
        change = f"{sign}{pct:.2f}%"
    pe = info.get("trailingPE", "")
    if _num(pe) is not None:
        pe = round(pe, 2)
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


_YAHOO_CHART_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")
_YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
_STOCK_DEADLINE_S = 8.0
_STOCK_HTTP_TIMEOUT = httpx.Timeout(4.0, connect=3.0)
_PE_BUDGET_S = 1.0
_PE_MAX_INFLIGHT = 4
_pe_inflight = 0


class SymbolNotFound(Exception):
    pass


def chart_to_info(payload: dict) -> dict:
    chart = payload.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        return {}
    res = results[0] or {}
    meta = res.get("meta") or {}
    price = _num(meta.get("regularMarketPrice"))
    if not price or price <= 0:
        return {}
    quotes = ((res.get("indicators") or {}).get("quote") or [{}])[0] or {}
    closes = [c for c in (_num(c) for c in quotes.get("close") or []) if c]
    prev = _num(meta.get("previousClose"))
    if not prev and len(closes) >= 2:
        prev = closes[-2]
    info = {
        "regularMarketPrice": round(price, 4),
        "currency": meta.get("currency") or "",
        "longName": meta.get("longName") or "",
        "shortName": meta.get("shortName") or "",
        "fiftyTwoWeekHigh": meta.get("fiftyTwoWeekHigh") or "",
        "fiftyTwoWeekLow": meta.get("fiftyTwoWeekLow") or "",
    }
    pct = _num(meta.get("regularMarketChangePercent"))
    if pct is not None:
        info["changePercent"] = pct
    if prev:
        info["previousClose"] = prev
    return info


async def _yahoo_chart(client: httpx.AsyncClient, sym: str) -> dict:
    path = f"/v8/finance/chart/{quote(sym, safe='')}"
    last: Exception | None = None
    for host in _YAHOO_CHART_HOSTS:
        try:
            resp = await client.get(host + path, params={"interval": "1d", "range": "5d"})
        except httpx.HTTPError as e:
            last = e
            continue
        if resp.status_code == 404:
            raise SymbolNotFound(sym)
        if resp.status_code == 429 or resp.status_code >= 500:
            last = httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=resp.request, response=resp)
            continue
        resp.raise_for_status()
        info = chart_to_info(resp.json())
        if not info:
            raise SymbolNotFound(sym)
        return info
    raise last or RuntimeError("Yahoo chart unavailable")


def _yf_info_sync(sym: str) -> dict:
    import yfinance as yf

    return dict(yf.Ticker(sym).info or {})


_PE_EXECUTOR = ThreadPoolExecutor(max_workers=_PE_MAX_INFLIGHT, thread_name_prefix="pe-lookup")


def _pe_done(_future) -> None:
    global _pe_inflight
    _pe_inflight -= 1


async def _pe_lookup(sym: str) -> object:
    global _pe_inflight
    _pe_inflight += 1
    future = _PE_EXECUTOR.submit(_yf_info_sync, sym)
    future.add_done_callback(_pe_done)
    info = await asyncio.wrap_future(future)
    pe = _num((info or {}).get("trailingPE"))
    return pe if pe and pe > 0 else ""


def _start_pe_lookups(candidates: list[str]) -> dict[str, asyncio.Task]:
    eligible = [s for s in candidates if not s.startswith("^") and "=" not in s]
    if not eligible or _PE_BUDGET_S <= 0 or _pe_inflight + len(eligible) > _PE_MAX_INFLIGHT:
        return {}
    return {sym: asyncio.create_task(_pe_lookup(sym)) for sym in eligible}


async def _await_pe(task: asyncio.Task | None, deadline: float) -> object:
    if task is None:
        return ""
    remaining = deadline - time.perf_counter()
    if remaining <= 0 and not task.done():
        return ""
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=max(remaining, 0.001))
    except Exception:
        return ""


def _discard_tasks(tasks) -> None:
    for t in tasks:
        if not t.done():
            t.cancel()
        t.add_done_callback(lambda f: f.cancelled() or f.exception())


async def _resolve_candidates(candidates: list[str]) -> tuple[str, dict] | None:
    errors: list[BaseException] = []
    async with httpx.AsyncClient(
        timeout=_STOCK_HTTP_TIMEOUT, follow_redirects=True, headers=_YAHOO_HEADERS
    ) as client:
        tasks = [asyncio.create_task(_yahoo_chart(client, sym)) for sym in candidates]
        try:
            for sym, task in zip(candidates, tasks):
                try:
                    info = await task
                except SymbolNotFound:
                    continue
                except Exception as e:
                    logger.warning("Yahoo chart failed for %s: %r", sym, e)
                    errors.append(e)
                    continue
                return sym, info
        finally:
            _discard_tasks(tasks)
    if errors:
        raise errors[0]
    return None


async def _stock(symbol: str, candidates: list[str]) -> ToolOutput:
    started = time.perf_counter()
    pe_tasks = _start_pe_lookups(candidates)
    try:
        async with asyncio.timeout(_STOCK_DEADLINE_S):
            found = await _resolve_candidates(candidates)
        if found is None:
            return _empty(f"Could not fetch stock data for {symbol}: no price data available")
        sym, info = found
        pe = await _await_pe(pe_tasks.get(sym), started + _PE_BUDGET_S)
        if pe:
            info = {**info, "trailingPE": pe}
        result = _build_stock_result(sym, info)
        if not result:
            return _empty(f"Could not fetch stock data for {symbol}: no price data available")
        structured, readable = result
        return _ok(structured + "\n" + readable, "yahoo_chart")
    except TimeoutError:
        logger.warning("Stock lookup timed out for %s", symbol)
        return _error(f"Could not fetch stock data for {symbol}: timed out after {_STOCK_DEADLINE_S:.0f}s")
    except Exception as e:
        logger.warning("Stock lookup failed for %s: %r", symbol, e)
        return _error(f"Could not fetch stock data for {symbol}: {_short_err(e)}")
    finally:
        _discard_tasks(pe_tasks.values())


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
