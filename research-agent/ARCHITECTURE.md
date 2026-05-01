# Alvoff Research Agent — Architecture

## Overview

The Research Agent is a NATS-driven microservice that handles all open-ended research and lookup queries from the Alvoff assistant ecosystem. It uses the [Deep Agents](../deepagents/) framework as its core reasoning engine — a middleware-based ReAct loop with planning, tool use, and automatic context compaction.

Queries that are not `email`, `calendar`, or `basic_chat` are classified as `research` by the Planning Agent and dispatched here via NATS JetStream.

**Core engine**: Deep Agents (ReAct loop with 8 custom tools).
**Output format**: Structured `ResearchResponse` with `blocks[]` — the frontend renders each block as a rich UI component (map, table, chart, markdown).
**Travel queries**: Flights, trains, and buses are handled via `web_search` — pulling structured results from ixigo, indiarailinfo, railyatri, redBus, and Google Flights aggregators. No dedicated travel API is integrated (datacenter IP restrictions make flight scrapers unreliable on Hetzner).

---

## Position in the Alvoff Ecosystem

```
User (WhatsApp / Web)
        │
        ▼
  Chat Gateway
        │
        ▼
 Planning Agent ──────────────────────────────────────┐
  │  classify_intents()                               │
  │                                                   │
  ├── basic_chat ──► Nomi LangGraph (in-process)     │
  ├── email ────────► Email Agent (NATS)              │
  ├── calendar ─────► Scheduling Agent (NATS)         │
  └── research ─────► Research Agent (NATS) ◄─────────┘
                             │
                    Deep Agents ReAct loop
                    (web search, news, stocks,
                     local places, forex, crypto,
                     Wikipedia, PDFs, flights,
                     trains, buses)
                             │
                    block_formatter
                    (tool results → blocks[])
                             │
                    NATS: ResearchResponse
                    (checkpoint events + structured blocks)
                             │
                    Planning Agent broadcasts
                    to WebSocket / WhatsApp
                             │
                    Frontend ResearchRenderer
                    (map, table, chart, markdown)
```

---

## Request Flow

```
1. User sends: "EV charging stations in Lucknow"

2. Planning Agent
   └── classify_intents() → action/research
   └── WorkflowEngine.handle_message() → FlowResult(handled=False)  [no flow registered]
   └── publish_action_request()
       → NATS: {env}.actions.research.request.conversation.{conv_id}

3. Research Agent — NATS Consumer
   └── Dedup check (Redis SET NX EX)
   └── Parse NATSActionRequest
   └── Build messages (conversation_history + current query)
   └── publish_checkpoint("Researching your query...")
   └── agent.astream_events({"messages": [...]}, version="v2")

4. Deep Agents ReAct Loop
   ├── write_todos(["Search for EV charging in Lucknow", "Find addresses and details"])
   │   └── checkpoint: "Organizing research plan..."
   │
   ├── web_search("EV charging stations Lucknow 2025")
   │   └── Exa neural search → cache miss → Exa API called
   │   └── checkpoint: "Searching the web for: 'EV charging stations Lucknow 2025'..."
   │   └── 5 results returned, cached in Redis (1hr TTL)
   │   └── checkpoint: "Found 5 results. Analyzing..."
   │   └── tool_result saved → block_formatter picks up later
   │
   ├── nearby_places("Lucknow", "charging_station", radius_m=5000)
   │   └── Nominatim geocodes "Lucknow" → lat/lng
   │   └── OSM Overpass API radius query → 8 stations with coordinates
   │   └── checkpoint: "Found 8 nearby charging stations. Analyzing..."
   │   └── tool_result saved → block_formatter creates leaflet-map + data-table
   │
   └── LLM synthesizes results → final AIMessage (markdown text)

5. Research Agent — block_formatter
   └── final_text → MarkdownBlock
   └── nearby_places result → LeafletMapBlock + DataTableBlock
   └── assemble ResearchResponse { query, blocks[], sources[] }

6. Research Agent — publisher
   └── publish_research_blocks(ResearchResponse)
       → NATS: {env}.actions.research.response.conversation.{conv_id}

7. Planning Agent — NATS Subscriber
   └── handle_action_response()
   └── Update ChatActionTask (completed)
   └── Broadcast research_blocks frame to WebSocket

8. Frontend — ResearchRenderer
   └── reads blocks[] array
   └── MarkdownBlock    → <MarkdownCard>     (summary text)
   └── LeafletMapBlock  → <LeafletMapCard>   (interactive map with 8 pins)
   └── DataTableBlock   → <DataTableCard>    (sortable table: Name, Address, Distance)
```

---

## Component Architecture

```
alvoff-assistant-research-agent/
├── src/research_agent/
│   ├── __init__.py               # uvicorn entrypoint
│   ├── config.py                 # pydantic-settings (all env vars)
│   ├── server.py                 # FastAPI app + lifespan (NATS, Redis, consumer)
│   │
│   ├── agent/
│   │   ├── graph.py              # create_deep_agent() singleton + system prompt
│   │   └── tools.py              # 8 custom tools with Redis caching
│   │
│   ├── consumer/
│   │   ├── handler.py            # NATS subscriber + astream_events loop
│   │   ├── publisher.py          # publish_checkpoint / publish_research_blocks / error
│   │   ├── schemas.py            # NATSActionRequest + ResearchResponse (blocks[])
│   │   ├── block_formatter.py    # tool results → structured blocks[]
│   │   └── checkpoint_formatter.py  # tool_name → user-visible progress message
│   │
│   └── infrastructure/
│       ├── nats_client.py        # NATS + JetStream singleton
│       └── redis_client.py       # Redis (dedup + tool result cache)

alvoff-assistant-fe/
└── src/research/
    ├── ResearchRenderer.jsx      # block dispatcher over blocks[]
    ├── blockStore.js             # zustand store — block state per report_id
    └── blocks/
        ├── MarkdownCard.jsx
        ├── DataTableCard.jsx
        ├── InsightCardsCard.jsx
        ├── LeafletMapCard.jsx    # location queries (nearby_places tool)
        └── BarChartCard.jsx
```

---

## Deep Agents Framework

The agent is built on [Deep Agents](../deepagents/libs/deepagents/) — a middleware-based orchestration harness over LangGraph.

### What `create_deep_agent()` gives us automatically

| Capability | How |
|---|---|
| **Planning** | `write_todos` tool — agent breaks complex tasks into steps before executing |
| **Intermediate notes** | `write_file` / `read_file` — saves research findings mid-task, reads them back for synthesis |
| **Auto context compaction** | `SummarizationMiddleware` — summarizes conversation at 85% token threshold |
| **Tool call repair** | `PatchToolCallsMiddleware` — repairs dangling tool calls if execution is interrupted |
| **ReAct loop** | LangGraph-managed agent → tools → agent loop until task complete |

### Middleware Stack (auto-applied)

```
TodoListMiddleware       ← write_todos planning
FilesystemMiddleware     ← read_file / write_file / glob / grep
SubAgentMiddleware       ← task() delegation (unused in v1)
SummarizationMiddleware  ← auto-compact at 85% context window
PatchToolCallsMiddleware ← repair interrupted tool calls
[User middleware]        ← none in v1
PermissionMiddleware     ← filesystem access control (always last)
```

---

## Tool Set

### Custom Tools (8 tools)

#### `web_search(query: str)`
- **Primary**: Exa neural/semantic search API (`exa-py`)
- **Fallback 1**: Tavily search API
- **Fallback 2**: DuckDuckGo (`duckduckgo-search`, no key)
- **Cache**: Redis, TTL 3600s (1 hour)
- **Use for**: General research, news, competitor analysis, government policy, product comparisons — and **all travel queries** (flights, trains, buses). Travel aggregators (ixigo, indiarailinfo, railyatri, redBus, Google Flights) surface in Exa/Tavily results with structured fare and schedule data.

#### `read_webpage(url: str)`
- **Primary**: Jina Reader (`r.jina.ai/{url}`) — returns clean Markdown
- **Fallback 1**: PyMuPDF (`fitz`) for complex PDFs
- **Fallback 2**: Return search snippet with explanation
- **Cache**: Redis, TTL 21600s (6 hours)
- **Use for**: Reading full article content, government PDFs (RBI circulars, SEBI notifications, Ministry docs), annual reports

#### `wiki_search(query: str)`
- **Engine**: Wikipedia API (`wikipedia-api` package)
- **Cache**: Redis, TTL 86400s (24 hours)
- **Use for**: Factual queries, definitions, historical information, overviews

#### `nearby_places(place: str, place_type: str, radius_meters: int)`
- **Geocoder**: Nominatim (OpenStreetMap) — converts place name to lat/lng
- **Search**: OSM Overpass API — radius query for amenity type
- **Cache**: Redis, TTL 86400s (24 hours)
- **Use for**: "Nearest X near Y" queries with GPS-level precision (fuel stations, hospitals, ATMs, EV chargers)
- **Block output**: → `leaflet-map` + `data-table`

#### `latest_news(topic: str)`
- **Sources**: RSS feeds — NDTV Top Stories, Economic Times, Moneycontrol, Times of India
- **Latency**: ~2–5 minutes from publication
- **Cache**: Redis, TTL 900s (15 minutes)
- **Block output**: → `data-table` (headline list)

#### `get_stock_price(symbol: str)`
- **Engine**: `yfinance` — NSE (`.NS`), BSE (`.BO`), Nifty 50 (`^NSEI`), Sensex (`^BSESN`)
- **Cache**: Redis, TTL 900s (15 minutes)
- **Block output**: → `insight-cards`

#### `get_forex_rate(from_currency: str, to_currency: str)`
- **Engine**: Frankfurter API (`api.frankfurter.app`) — completely free, no key
- **Cache**: Redis, TTL 3600s (1 hour)
- **Block output**: → `insight-cards`

#### `get_crypto_price(coin_id: str)`
- **Engine**: CoinGecko API — free tier, no key for basic endpoints
- **Cache**: Redis, TTL 300s (5 minutes)
- **Block output**: → `insight-cards`

### Deep Agents Built-in Tools (automatic)

| Tool | Purpose |
|---|---|
| `write_todos` | Agent plans research steps before executing (complex multi-step queries) |
| `write_file` | Saves intermediate findings to in-memory state during research |
| `read_file` | Reads back saved notes for synthesis |
| `glob` / `grep` | Searches within saved research notes |

---

## Structured Block Output

### How It Works

Deep Agents runs its ReAct loop as normal. The `handler.py` captures every `on_tool_end` event and stores the raw tool result alongside the tool name. After `on_chat_model_end` fires (agent done), `block_formatter.py` converts the agent's text output + tool results into a `ResearchResponse`:

```
Deep Agent finishes
        │
        ▼
block_formatter(final_text, tool_results, query)
        │
        ├── Always:  MarkdownBlock(final_text)         ← lead summary
        │
        ├── If nearby_places was called:
        │   ├── LeafletMapBlock(markers from OSM result)
        │   └── DataTableBlock(name, address, distance rows)
        │
        ├── If get_stock_price / get_crypto_price / get_forex_rate called:
        │   └── InsightCardsBlock(price, change, stats)
        │
        └── If latest_news called:
            └── DataTableBlock(headline, source, published rows)
```

### Block Schema

```python
# Always present
MarkdownBlock    → { template_id: "markdown",      data: { content: str } }

# Location queries (nearby_places tool)
LeafletMapBlock  → { template_id: "leaflet-map",   data: { center, zoom, markers[] } }
DataTableBlock   → { template_id: "data-table",    data: { columns[], rows[] } }

# Financial queries (stock / crypto / forex tools)
InsightCardsBlock → { template_id: "insight-cards", data: { items[] } }

# News queries (latest_news tool)
DataTableBlock   → { template_id: "data-table",    data: { columns[], rows[] } }
```

### Tool → Block Mapping

| Tool called | Extra blocks added |
|---|---|
| `nearby_places` | `leaflet-map` + `data-table` |
| `get_stock_price` | `insight-cards` (price, P/E, 52w range) |
| `get_crypto_price` | `insight-cards` (price INR/USD, 24h change) |
| `get_forex_rate` | `insight-cards` (rate, timestamp) |
| `latest_news` | `data-table` (headline, source, published) |
| `web_search` | none — text folded into `markdown` summary |
| `wiki_search` | none — text folded into `markdown` summary |
| `read_webpage` | none — content used in `markdown` synthesis |

### ResearchResponse (NATS payload)

```json
{
  "query": "EV charging stations in Lucknow",
  "blocks": [
    {
      "template_id": "markdown",
      "data": { "content": "Found 8 EV charging stations in Lucknow. Tata Power has the widest coverage..." }
    },
    {
      "template_id": "leaflet-map",
      "data": {
        "center": { "lat": 26.8467, "lon": 80.9462 },
        "zoom": 12,
        "markers": [
          { "lat": 26.851, "lon": 80.949, "label": "Tata Power - Hazratganj", "popup": "Type 2, 22kW" },
          { "lat": 26.863, "lon": 80.962, "label": "Ather Grid - Gomti Nagar", "popup": "Fast, 60kW" }
        ]
      }
    },
    {
      "template_id": "data-table",
      "data": {
        "columns": ["Name", "Area", "Charger Type", "Power"],
        "rows": [
          { "Name": "Tata Power", "Area": "Hazratganj", "Charger Type": "Type 2", "Power": "22kW" },
          { "Name": "Ather Grid", "Area": "Gomti Nagar", "Charger Type": "Fast Charge", "Power": "60kW" }
        ]
      }
    }
  ],
  "sources": ["https://www.openstreetmap.org/...", "https://..."]
}
```

---

## NATS Integration

### Streams (owned by Planning Agent — not created here)

| Stream | Subject pattern | Type |
|---|---|---|
| `{env}_ACTION_REQUESTS` | `{env}.actions.*.request.>` | LIMITS |
| `{env}_ACTION_RESPONSES` | `{env}.actions.*.response.conversation.*` | INTEREST |

### Subjects used by Research Agent

| Direction | Subject |
|---|---|
| Subscribe (inbound) | `{env}.actions.research.request.>` |
| Publish checkpoint | `{env}.actions.research.response.conversation.{conv_id}` |
| Publish result | `{env}.actions.research.response.conversation.{conv_id}` |

### Consumer Configuration

| Parameter | Value | Reason |
|---|---|---|
| Durable name | `{env}_research_agent_group` | Queue group for load balancing |
| ACK wait | 300s (5 min) | Covers 3–5 web searches + LLM inference |
| Max ACK pending | 10 | Research is compute-heavy, low concurrency by design |
| Manual ACK | Yes | ACK only after successful publish |

### Message Types Published

```json
// Checkpoint (real-time progress — same as email/scheduling agents)
{
  "type": "checkpoint",
  "status": "in_progress",
  "content": "Searching the web for: 'EV charging stations Lucknow'...",
  "sender": "alvoff",
  "action_type": "research",
  "task_id": "...",
  "conversation_id": 123
}

// Final result (structured blocks — new for research agent)
{
  "type": "research_blocks",
  "status": "completed",
  "sender": "alvoff",
  "action_type": "research",
  "task_id": "...",
  "conversation_id": 123,
  "data": {
    "query": "...",
    "blocks": [...],
    "sources": [...]
  }
}

// Error (fallback — plain text if block formatting fails)
{
  "type": "error",
  "status": "failed",
  "content": "Sorry, I couldn't complete your research request. Please try again.",
  "sender": "alvoff",
  "action_type": "research",
  "task_id": "...",
  "conversation_id": 123
}
```

---

## Streaming Checkpoint Events

Every tool call during the ReAct loop emits a real-time checkpoint to the frontend:

```
Deep Agent astream_events()              NATS publish → WebSocket
─────────────────────────────            ──────────────────────────────
on_tool_start(write_todos)           →   [Alvoff] Organizing research plan...
on_tool_end(write_todos)             →   [Alvoff] Research plan ready. Starting...
on_tool_start(web_search, q=...)     →   [Alvoff] Searching the web for: "..."...
on_tool_end(web_search)              →   [Alvoff] Found 5 results. Analyzing...
on_tool_start(nearby_places, ...)    →   [Alvoff] Searching for charging_station near Lucknow...
on_tool_end(nearby_places)           →   [Alvoff] Found 8 nearby locations. Analyzing...
on_tool_start(get_stock_price, ...)  →   [Alvoff] Fetching stock price for RELIANCE...
on_tool_end(get_stock_price)         →   [Alvoff] Got market data.
on_tool_start(latest_news, ...)      →   [Alvoff] Checking latest news on "RBI rate"...
on_tool_end(latest_news)             →   [Alvoff] Got 6 news articles. Analyzing...
on_tool_start(web_search, q=flights) →   [Alvoff] Searching the web for: "flights Bangalore to Jaipur..."...
on_tool_end(web_search)              →   [Alvoff] Found 5 results. Analyzing...
on_chat_model_end(AIMessage)         →   [captured — final_text + tool_results]
                                         ↓
                                     block_formatter()
                                         ↓
                                     [Alvoff] research_blocks { blocks: [...] }
```

---

## Frontend Block Rendering

### ResearchRenderer (alvoff-assistant-fe)

```jsx
const COMPONENTS = {
  "markdown":      MarkdownCard,
  "data-table":    DataTableCard,
  "insight-cards": InsightCardsCard,
  "leaflet-map":   LeafletMapCard,
  "bar-chart":     BarChartCard,
};

export function ResearchRenderer({ blocks }) {
  return (
    <div className="research-stack">
      {blocks.map((block, i) => {
        const C = COMPONENTS[block.template_id];
        return C ? <C key={i} {...block.data} /> : null;
      })}
    </div>
  );
}
```

### WS Frame Handler

```js
case "research_blocks":
  blockStore.setReport(frame.data);
  // triggers ResearchRenderer to render blocks[]
  break;

case "checkpoint":
  // existing pattern — shows progress in ConsoleEntry / chat bubble
  break;
```

### Block Components

| Component | Renders | New deps needed |
|---|---|---|
| `MarkdownCard.jsx` | Markdown text | none (already in app) |
| `DataTableCard.jsx` | Sortable table | none |
| `InsightCardsCard.jsx` | Severity-colored cards | none |
| `LeafletMapCard.jsx` | Interactive map with pins | `leaflet`, `react-leaflet` |
| `BarChartCard.jsx` | Bar chart | `recharts` (already installed) |

---

## Caching Architecture

Two layers of caching are applied:

### Layer 1 — Tool Result Caching (Redis)

Every tool function wraps external API calls with a Redis cache check:

```
Tool called
    │
    ▼
Redis GET research:{tool}:{hash(args)}
    │
    ├── HIT  → return cached value instantly (zero API cost)
    │
    └── MISS → call external API
                    │
                    ▼
               store in Redis with TTL
                    │
                    ▼
               return result
```

| Tool | Cache key pattern | TTL |
|---|---|---|
| `web_search` | `research:search:{sha256(query)[:16]}` | 3600s |
| `read_webpage` | `research:page:{sha256(url)[:16]}` | 21600s |
| `wiki_search` | `research:wiki:{sha256(query)[:16]}` | 86400s |
| `nearby_places` | `research:osm:{sha256(place+type+radius)[:16]}` | 86400s |
| `latest_news` | `research:news:{sha256(topic)[:16]}` | 900s |
| `get_stock_price` | `research:stock:{symbol.upper()}` | 900s |
| `get_forex_rate` | `research:forex:{from}:{to}` | 3600s |
| `get_crypto_price` | `research:crypto:{coin_id}` | 300s |

### Layer 2 — LLM Prompt Caching (OpenRouter)

The research agent's system prompt (~2000 tokens) is cached server-side via OpenRouter's prompt caching feature for Claude models:

```python
model_kwargs={
    "extra_body": {
        "cache_control": {"type": "ephemeral"}
    }
}
```

---

## LLM Configuration

| Setting | Value |
|---|---|
| Primary | OpenRouter → `anthropic/claude-sonnet-4-6` |
| Fallback | OpenAI → `gpt-4o` |
| Temperature | 0.3 (focused, factual) |
| Prompt caching | Enabled via OpenRouter `cache_control: ephemeral` |
| Framework | `ChatOpenAI` pointed at OpenRouter base URL |

---

## What the Agent Can Handle

### Query Categories & Examples

#### Local & Maps
| Query | Tool used | Blocks |
|---|---|---|
| "EV charging stations in Lucknow" | `nearby_places` | markdown + leaflet-map + data-table |
| "Hospitals near Koramangala Bangalore" | `nearby_places` | markdown + leaflet-map + data-table |
| "ATMs within 1km of Connaught Place" | `nearby_places` | markdown + leaflet-map + data-table |
| "Petrol pumps near me" (with coordinates) | `nearby_places` | markdown + leaflet-map + data-table |

#### Financial
| Query | Tool used | Blocks |
|---|---|---|
| "Infosys share price today" | `get_stock_price` | markdown + insight-cards |
| "Nifty 50 / Sensex level" | `get_stock_price` | markdown + insight-cards |
| "1000 USD to INR today" | `get_forex_rate` | markdown + insight-cards |
| "Bitcoin price in rupees" | `get_crypto_price` | markdown + insight-cards |
| "Top 5 IT stocks on NSE" | `web_search` | markdown |

#### News & Current Events
| Query | Tool used | Blocks |
|---|---|---|
| "Latest RBI interest rate decision" | `latest_news` | markdown + data-table |
| "GST council meeting updates" | `latest_news` | markdown + data-table |
| "Budget 2025 announcements" | `latest_news` + `web_search` | markdown + data-table |
| "Sensex crash today news" | `latest_news` | markdown + data-table |

#### Travel (via web_search — no dedicated API)
| Query | Sources pulled from | Blocks |
|---|---|---|
| "Flights from Bangalore to Jaipur" | Google Flights, ixigo, Skyscanner, Trip.com | markdown (fare ranges + booking links) |
| "Cheapest flight Mumbai to Goa on 15 June" | ixigo, MakeMyTrip, IndiGo, Air India | markdown |
| "Trains from Bengaluru to Bikaner" | indiarailinfo.com, railyatri.in, ixigo.com | markdown (schedule + fares by class) |
| "IRCTC trains Delhi to Varanasi tomorrow" | indiarailinfo.com, NTES, ixigo | markdown |
| "Buses from Bangalore to Goa" | redBus, KSRTC, AbhiBus | markdown |
| "KSRTC sleeper bus Pune to Mumbai" | redBus, MSRTC website | markdown |

> **Note on Travel**: `web_search` pulls from travel aggregators (ixigo, railyatri, redBus) that already have structured data. Results include fare ranges, schedules, class availability, and booking links — sufficient for planning. Dedicated flight/train APIs were evaluated but ruled out due to datacenter IP restrictions on Hetzner (Google blocks scrapers; Amadeus/IRCTC require production approval).

#### Research & Analysis
| Query | Tool used | Blocks |
|---|---|---|
| "Reliance Jio competitors analysis" | `web_search` | markdown |
| "RBI circular on NBFC regulations" | `web_search` + `read_webpage` | markdown |
| "SEBI new F&O rules 2024" | `web_search` + `read_webpage` | markdown |
| "What is MSME definition in India" | `wiki_search` | markdown |
| "Tesla EV competitors in Indian market" | `web_search` | markdown |

#### General Knowledge
| Query | Tool used | Blocks |
|---|---|---|
| "Weather in Chennai today" | `web_search` | markdown |
| "Aadhaar card update process" | `web_search` | markdown |
| "PM Mudra loan scheme details" | `web_search` + `wiki_search` | markdown |
| "EPFO passbook balance check" | `web_search` | markdown |

### Not Covered

| Category | Reason |
|---|---|
| Live intraday tick / options chain | Broker API (Zerodha, Angel) needed |
| Real-time traffic / route navigation | Google Maps API needed |
| Paywalled content | By design — Jina/PyMuPDF cannot bypass paywalls |
| Scanned PDFs (OCR) | Deferred — Tesseract not integrated |
| Social media trends | Twitter/X API is paid |
| PNR status (real-time) | IRCTC has no public API; NTES web scraping is fragile |
| Seat availability (exact) | Requires IRCTC login session |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_ENV` | Yes | Environment prefix for NATS subjects (`dev`/`staging`/`prod`) |
| `PORT` | No | HTTP port (default: 8004) |
| `NATS_URL` | Yes | NATS server URL |
| `NATS_JS_ACK_WAIT` | No | Consumer ACK wait in seconds (default: 300) |
| `NATS_JS_MAX_ACK_PENDING` | No | Max concurrent messages (default: 10) |
| `REDIS_URL` | Yes | Redis URL for dedup + tool result caching |
| `DEDUP_TTL` | No | Dedup key TTL in seconds (default: 86400) |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key (primary LLM) |
| `OPENROUTER_MODEL` | No | Model name (default: `anthropic/claude-sonnet-4-6`) |
| `OPENROUTER_BASE_URL` | No | OpenRouter base URL |
| `OPENAI_API_KEY` | No | OpenAI fallback key |
| `OPENAI_MODEL` | No | OpenAI fallback model (default: `gpt-4o`) |
| `LLM_TEMPERATURE` | No | LLM temperature (default: 0.3) |
| `EXA_API_KEY` | Yes | Exa search API key (primary web search) |
| `EXA_MAX_RESULTS` | No | Max results per search (default: 5) |
| `TAVILY_API_KEY` | Yes | Tavily API key (fallback web search) |
| `TAVILY_MAX_RESULTS` | No | Max results (default: 5) |
| `TAVILY_SEARCH_DEPTH` | No | `basic` or `advanced` (default: `advanced`) |
| `JINA_API_KEY` | No | Jina Reader API key (optional, free tier works without) |

**No keys needed for:** Wikipedia, OSM Overpass, Nominatim, yfinance, Frankfurter API, CoinGecko, RSS feeds, PyMuPDF, DuckDuckGo.

---

## Health Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness — returns immediately |
| `GET /health/ready` | Readiness — checks NATS, Redis, Exa reachability |
| `GET /metrics` | Prometheus metrics (via `prometheus-fastapi-instrumentator`) |

---

## Dependencies

| Package | Purpose |
|---|---|
| `deepagents` | Core agent framework (local editable path) |
| `langchain-openai` | ChatOpenAI for OpenRouter + fallback |
| `langchain-core` / `langchain` | LangChain base |
| `langgraph` | Graph execution engine (used by deepagents) |
| `fastapi` + `uvicorn` | HTTP server + health endpoints |
| `nats-py[nkeys]` | NATS JetStream consumer |
| `redis` | Dedup + tool result cache |
| `exa-py` | Exa neural search |
| `httpx` | HTTP client for Tavily, Jina, Frankfurter, CoinGecko, OSM |
| `yfinance` | Stock price data |
| `feedparser` | RSS feed parsing |
| `wikipedia-api` | Wikipedia search |
| `duckduckgo-search` | Last-resort search fallback |
| `pymupdf` | PDF text extraction fallback |
| `pydantic-settings` | Environment variable management |
| `prometheus-fastapi-instrumentator` | Metrics |

**Frontend (alvoff-assistant-fe):**

| Package | Purpose |
|---|---|
| `leaflet` + `react-leaflet` | Interactive map for `leaflet-map` blocks |
| `zustand` | Block state store for ResearchRenderer |
| `recharts` | Bar/line charts (likely already installed) |
