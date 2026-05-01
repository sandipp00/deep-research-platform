# Research Agent — Architecture

A FastAPI service that runs a Deep Agents ReAct loop with 8 custom tools and streams structured research blocks back over Server-Sent Events.

## Position in the stack

```
React UI ──► Spring Boot backend ──► Research Agent (this service)
   ▲                ▲                       │
   │                │                       ├─► Redis (tool result cache)
   │                │                       ├─► OpenRouter / OpenAI (LLM)
   └── SSE ─────────┴── SSE ─────────────── ┴─► Exa / Tavily / DuckDuckGo
                                              OSM, yfinance, RSS, Frankfurter,
                                              CoinGecko, Wikipedia, Jina/PyMuPDF
```

The Spring Boot backend authenticates the user, persists the conversation, calls `POST /research` here, and proxies the SSE events back to the React frontend.

## Request lifecycle

```
1. POST /research
   Body: { "query": "...", "conversation_history": [{role, content}, ...] }

2. SSE stream opens
   ├─► event: checkpoint   data: {status, content, tool?}    (per tool call)
   ├─► event: checkpoint   data: ...
   ├─► event: blocks       data: {status, data: ResearchResponse}
   │                       OR
   │   event: clarification data: {status, content}
   │                       OR
   │   event: error        data: {status, content}
   └─► event: done         data: {status: "completed"}
```

`blocks`, `clarification`, and `error` are mutually exclusive terminal events — exactly one fires per request, then `done` closes the stream.

## Internal flow

```
http_handler.stream_research(req)
        │
        ├── _build_messages()              # history + today's date → list[BaseMessage]
        │
        ├── agent = await get_agent()      # singleton, lazy-init
        │
        ├── async for event in agent.astream_events(..., version="v2"):
        │     ├── on_tool_start  → checkpoint_formatter.format_tool_start  → SSE checkpoint
        │     ├── on_tool_end    → block_formatter.ToolResult collected
        │     │                  → checkpoint_formatter.format_tool_end    → SSE checkpoint
        │     └── on_chat_model_end → final_text captured
        │
        ├── if final_text starts with "[CLARIFICATION]"
        │      → SSE clarification → done
        │
        ├── else
        │      ├── format_blocks(final_text, tool_results, query) → ResearchResponse
        │      ├── generate_follow_ups(...)  with 3s timeout, best-effort
        │      └── SSE blocks → done
        │
        └── on exception → SSE error → done
```

## Tools

All 8 tools wrap their external API call with a Redis cache check.

| Tool | Engine(s) | TTL | Block(s) appended |
|---|---|---|---|
| `web_search` | Exa → Tavily → DuckDuckGo | 1 h | none (text into markdown) |
| `read_webpage` | Jina Reader → PyMuPDF | 6 h | none |
| `wiki_search` | Wikipedia API | 24 h | none |
| `nearby_places` | Nominatim + OSM Overpass | 24 h | leaflet-map + data-table |
| `latest_news` | RSS (NDTV, ET, Moneycontrol, TOI) | 15 m | data-table |
| `get_stock_price` | yfinance | 15 m | insight-cards |
| `get_forex_rate` | Frankfurter (free) | 1 h | insight-cards |
| `get_crypto_price` | CoinGecko (free) | 5 m | insight-cards |

Tool outputs use pipe-delimited prefixes (`PLACE|`, `STOCK|`, `NEWS|`, etc.) so `block_formatter` can reliably parse them out into structured blocks.

## Block types

| `template_id` | Data shape | When emitted |
|---|---|---|
| `markdown` | `{ content: string }` | Always — the agent's prose answer |
| `data-table` | `{ columns[], rows[] }` | After `nearby_places` or `latest_news` |
| `insight-cards` | `{ items: [{title, body, severity}] }` | After `get_stock_price` / `get_forex_rate` / `get_crypto_price` |
| `leaflet-map` | `{ center, zoom, markers[] }` | After `nearby_places` |

The frontend's `BlockRenderer` dispatches on `template_id`; unknown ids fall back to a JSON viewer so adding a new block server-side never breaks the UI.

## Source layout

```
src/research_agent/
├── __init__.py                 # uvicorn entry: research_agent:main
├── server.py                   # FastAPI app + lifespan + /research endpoint
├── http_handler.py             # the SSE generator (stream_research)
├── config.py                   # pydantic-settings (env vars)
├── agent/
│   ├── graph.py                # Deep Agent singleton + LLM wiring
│   └── tools.py                # the 8 tools, all Redis-cached
├── blocks/
│   ├── schemas.py              # pydantic block + ResearchResponse models
│   ├── block_formatter.py      # tool results → structured blocks
│   ├── checkpoint_formatter.py # tool name + input → user-facing message
│   └── follow_up_generator.py  # OpenAI-backed suggestion generator
└── infrastructure/
    └── redis_client.py         # connect/disconnect + cache_get/cache_set
```

## Deep Agents — what it gives us

The agent is built with `create_deep_agent()` (middleware-based ReAct over LangGraph). For free we get:

- **`write_todos`** — agent plans steps before executing complex queries.
- **`read_file` / `write_file`** — in-memory scratch space for multi-step research.
- **Auto context compaction** — `SummarizationMiddleware` summarizes at ~85% of the context window.
- **Tool call repair** — interrupted tool calls get patched up automatically.
- **Filesystem permission middleware** — sandboxed file ops.

We don't write any of that — the framework handles it.

## LLM configuration

| Setting | Value |
|---|---|
| Primary | OpenRouter → `anthropic/claude-sonnet-4-6` (configurable via `OPENROUTER_MODEL`) |
| Fallback | OpenAI → `gpt-4o` |
| Temperature | 0.3 |
| Prompt caching | OpenRouter `cache_control: ephemeral` on the system prompt |

If neither key is set, `_build_model()` raises at first request (the `/health/ready` endpoint surfaces the missing key).

## Caching

Every tool wraps its external call:

```
key = f"research:{tool}:{sha256(args)[:16]}"
cached = await cache_get(key)
if cached: return cached
result = await fetch_external()
await cache_set(key, result, ttl)
```

Cache misses fall through cleanly; cache failures are logged and treated as misses (never blocking).

## Health endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness — returns immediately |
| `GET /health/ready` | Readiness — Redis ping + LLM key check + search key check |
| `GET /metrics` | Prometheus metrics (`prometheus-fastapi-instrumentator`) |

## What it can / can't do

**Handles well**: local search ("EV chargers in Lucknow"), financial lookups (stocks/forex/crypto), Indian news, regulatory PDFs, competitor research, general queries, travel via aggregator search (ixigo, redBus, indiarailinfo).

**Out of scope**: live intraday options chains (broker API needed), Google Maps routing, paywalled content, scanned-PDF OCR, social media trends, IRCTC PNR/seat availability (no public API).
