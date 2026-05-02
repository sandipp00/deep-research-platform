# Lumen — Deep Research Platform

A full-stack AI research assistant. Type a question in any language, an autonomous agent picks the right tools (web search, maps, finance APIs, news, Wikipedia, PDF reader…), executes a multi-step ReAct loop, and streams back rich UI blocks — markdown, sortable tables, interactive maps, severity-colored insight cards — with live progress checkpoints.

```
┌──────────────┐   HTTP + SSE    ┌──────────────────┐   HTTP + SSE   ┌─────────────────────┐
│  React UI    │◄───────────────►│ Spring Boot API  │◄──────────────►│ Python Research     │
│  (TypeScript)│   JWT auth      │ + PostgreSQL     │                │ Agent (FastAPI)     │
│              │                 │ + Redis cache    │                │ + Deep Agents (LLM) │
└──────────────┘                 └──────────────────┘                └─────────────────────┘
```

## Tech stack — and why

### Frontend (`frontend/`)

| Tech | Version | Why we chose it |
|---|---|---|
| **React** | 18.3 | Industry standard, huge ecosystem, fits component-per-block model |
| **TypeScript** | 5.6 | Yes — the *entire* frontend is TypeScript. Block schemas / message types / API responses are all typed end-to-end. Catches block-shape bugs at compile time, not at runtime in front of a user. |
| **Vite** | 5.4 | Sub-second HMR; replaces webpack/CRA |
| **Tailwind CSS** | 3.4 | Utility-first; design tokens live in `tailwind.config.ts` (gradients, dark theme, animations) |
| **Framer Motion** | 11.11 | Per-block stagger animations + checkpoint timeline transitions |
| **Zustand** | 5.0 | State management for `auth` + `chat` stores. Lighter than Redux, no boilerplate |
| **React Router** | 6.28 | `/login`, `/register`, `/c/:id` routing |
| **react-leaflet + leaflet** | 4.2 / 1.9 | Interactive maps for location queries |
| **react-markdown + remark-gfm** | 9.0 / 4.0 | GitHub-flavored markdown rendering inside chat bubbles |
| **lucide-react** | 0.460 | Tree-shakeable icon set, clean default style |
| **@microsoft/fetch-event-source** | 2.0 | Browser SSE that supports custom headers (built-in `EventSource` can't send `Authorization`) |
| **axios** | 1.7 | HTTP client with interceptor for auto-attaching JWT and 401 handling |

### Backend (`backend/`)

| Tech | Version | Why |
|---|---|---|
| **Java** | 21 (LTS) | Stable, modern records, virtual threads available |
| **Spring Boot** | 3.3 | De-facto Java web framework |
| **Spring Security** | 6.3 | JWT-based stateless auth; permits `DispatcherType.ASYNC` for SSE re-dispatch |
| **Spring Data JPA** | 3.3 | Repositories without writing SQL; transactions are `@Transactional` |
| **PostgreSQL** | 16 | Native `JSONB` support stores variable-shape research blocks elegantly |
| **Hypersistence Utils** | 3.9 | Maps `JSONB` columns to Java `List<Object>` via `@JdbcTypeCode` |
| **JJWT** | 0.12 | Compact JWT lib, signs HS256 |
| **Lombok** | latest | Removes 200 lines of getter/setter/constructor boilerplate |
| **Java HttpClient** | built-in | Streams the agent's SSE response — *forced to HTTP/1.1* (HTTP/2 negotiation breaks uvicorn body parsing) |
| **SseEmitter** | Spring built-in | Server-side SSE — long-lived response that pushes events as the agent produces them |
| **Maven** | 3.9 | Build / dependency management |

### Research agent (`research-agent/`)

| Tech | Version | Why |
|---|---|---|
| **Python** | 3.12 | Modern type hints (`list[str]`, `int \| None`), fast |
| **FastAPI** | 0.136 | Async-first, automatic OpenAPI, built-in validation via Pydantic |
| **Deep Agents** | 0.5.5 | ReAct middleware on top of LangGraph — plans, tool-calls, auto context compaction, file scratch space |
| **LangGraph** | 1.1 | Graph-based agent execution, used internally by Deep Agents |
| **LangChain Core** | 1.3 | Message abstractions, tool decorators |
| **OpenAI SDK** (via OpenRouter) | 2.33 | LLM calls — Claude Sonnet 4.6 by default, easy fallback to GPT-4o |
| **Pydantic v2** | 2.13 | Schema definition for blocks + request validation |
| **Redis** | server 7, client 7.4 | Tool-result cache (per-tool TTL: 5 min crypto, 24 h Wikipedia, 1 h web search) |
| **httpx** | 0.28 | Async HTTP for Tavily, Jina, Frankfurter, CoinGecko, OSM Overpass |
| **exa-py / duckduckgo-search** | latest | Search API stack: Exa primary → Tavily fallback → DDG last resort |
| **yfinance** | 1.3 | NSE/BSE/global stock data |
| **feedparser** | 6.0 | RSS for `latest_news` (NDTV, Economic Times, etc.) |
| **wikipedia-api** | 0.14 | Free Wikipedia |
| **pymupdf (fitz)** | 1.27 | PDF reading fallback when Jina Reader fails |

### Infrastructure

| Tech | Why |
|---|---|
| **Docker + Compose** | One command brings up postgres + redis + agent + backend. No "install Java + Maven + Python + uv on your laptop" dance. |
| **Postgres in Docker** | Mapped to host port `5433` to dodge any local Postgres on `5432`. |

## Architecture in one diagram

```
User types: "restaurants near Connaught Place Delhi"
          │
          ▼
┌────────────────────────┐
│  React (TypeScript)    │  POST /api/conversations/{id}/query
│  - BlockRenderer       │  Authorization: Bearer <JWT>
│  - SSE listener        │  Body: {"query": "..."}
└─────────┬──────────────┘
          │
          ▼
┌────────────────────────┐
│  Spring Boot           │  1. Persists user message in `messages` table
│  - JwtAuthFilter       │  2. Loads conversation history
│  - ResearchController  │  3. Opens SSE stream to Python agent
│  - SseEmitter          │  4. Forwards each SSE event to React
└─────────┬──────────────┘  5. After `done`, persists assistant message
          │                    + blocks (JSONB) + sources + follow_ups
          ▼
┌────────────────────────┐
│  FastAPI Research Agent│  POST /research → SSE
│  - Deep Agents loop    │
│  - 8 custom tools      │  ▲ on_tool_start  → emit checkpoint
│  - astream_events()    │  ▲ on_tool_end    → emit checkpoint
│                        │  ▲ on_chat_model_end → final text captured
└─────────┬──────────────┘  │
          │                 │  Redis cache
          ▼                 │  (per-tool, hashed args)
   External APIs:           │
   • Exa / Tavily / DDG     │  → web_search results cached 1h
   • OSM Overpass           │  → nearby_places cached 24h
   • yfinance               │  → stock prices cached 15min
   • CoinGecko              │  → crypto cached 5min
   • RSS feeds              │  → news cached 15min
   • Wikipedia              │  → wiki cached 24h
   • Jina / PyMuPDF         │  → page content cached 6h
   • OpenRouter (Claude)    │  → LLM with prompt caching
```

## The block system (the magic)

The agent doesn't just return text. Based on which tools it called, it emits a list of typed blocks:

| `template_id` | When emitted | Frontend component |
|---|---|---|
| `markdown` | always | `MarkdownBlock` (react-markdown + GFM) |
| `data-table` | after `nearby_places` or `latest_news` | `DataTableBlock` (sortable, link-aware) |
| `insight-cards` | after `get_stock_price` / `get_forex_rate` / `get_crypto_price` | `InsightCardsBlock` (severity-colored) |
| `leaflet-map` | after `nearby_places` | `LeafletMapBlock` (auto-fit bounds, brand pins) |
| **anything unknown** | future-proof | `FallbackBlock` (collapsible JSON viewer) |

The frontend's `BlockRenderer.tsx` is a `switch` on `template_id`. Anything new the agent invents tomorrow lands in `FallbackBlock` with no code change — the UI never breaks.

## Database schema (auto-generated by JPA)

```sql
users (
  id              UUID PRIMARY KEY,
  email           VARCHAR UNIQUE NOT NULL,
  password_hash   VARCHAR NOT NULL,         -- bcrypt
  name            VARCHAR NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL
)

conversations (
  id              UUID PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  title           VARCHAR NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL,
  updated_at      TIMESTAMPTZ NOT NULL
)

messages (
  id              UUID PRIMARY KEY,
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  role            VARCHAR(16) NOT NULL,    -- 'USER' | 'ASSISTANT'
  content         TEXT,
  blocks          JSONB,                   -- the typed block array
  sources         JSONB,                   -- citation URLs
  follow_ups      JSONB,                   -- suggested next questions
  created_at      TIMESTAMPTZ NOT NULL
)
```

`JSONB` lets us store an arbitrary list of blocks per message without a separate `blocks` table. Postgres can index inside JSONB if we ever need to query "messages that contain a leaflet-map block" — `WHERE blocks @> '[{"template_id":"leaflet-map"}]'`.

## API surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | — | `{email, password, name}` → `{token, id, email, name}` |
| POST | `/api/auth/login` | — | `{email, password}` → `{token, …}` |
| GET | `/api/auth/me` | Bearer | Current user |
| GET | `/api/conversations` | Bearer | List user's conversations |
| POST | `/api/conversations` | Bearer | Create empty conversation |
| GET | `/api/conversations/{id}` | Bearer | Single conversation |
| PATCH | `/api/conversations/{id}` | Bearer | Rename — `{title}` |
| DELETE | `/api/conversations/{id}` | Bearer | Delete |
| GET | `/api/conversations/{id}/messages` | Bearer | Full transcript with blocks |
| POST | `/api/conversations/{id}/query` | Bearer | `{query}` → SSE stream |

### SSE event types from `/query`

| event | data | When |
|---|---|---|
| `user_message` | `{id, createdAt}` | Right after the user's message is persisted |
| `checkpoint` | `{status, content, tool?}` | Per tool call from the agent |
| `blocks` | `{status, data: ResearchResponse}` | Final answer, terminal |
| `clarification` | `{status, content}` | Agent needs more info, terminal |
| `error` | `{status, content}` | Failure, terminal |
| `persisted` | `{messageId}` | Backend has stored the assistant message |

## Module breakdown

```
deep-research-platform/
├── frontend/                          # React + TS app
│   ├── src/
│   │   ├── components/
│   │   │   ├── blocks/                # one file per block type
│   │   │   │   ├── BlockRenderer.tsx  # the switch
│   │   │   │   ├── MarkdownBlock.tsx
│   │   │   │   ├── DataTableBlock.tsx
│   │   │   │   ├── LeafletMapBlock.tsx
│   │   │   │   ├── InsightCardsBlock.tsx
│   │   │   │   └── FallbackBlock.tsx
│   │   │   ├── ChatPanel.tsx          # main chat with SSE handling
│   │   │   ├── ChatInput.tsx          # auto-resize textarea
│   │   │   ├── CheckpointTrail.tsx    # streaming progress timeline
│   │   │   ├── MessageBubble.tsx      # user/assistant rendering
│   │   │   └── ConversationSidebar.tsx
│   │   ├── pages/                     # Login, Register, Chat
│   │   ├── store/                     # Zustand stores: auth, chat
│   │   ├── lib/                       # api.ts (axios), sse.ts (fetchEventSource)
│   │   ├── types.ts                   # all shared TS types
│   │   └── index.css                  # Tailwind layers + Leaflet dark filter
│   ├── tailwind.config.ts             # design tokens (TypeScript config)
│   └── vite.config.ts                 # build config (TypeScript)
│
├── backend/                           # Spring Boot
│   └── src/main/java/ai/alvoff/       # (package name kept; internal only)
│       ├── auth/                      # JWT auth: filter, service, controller, User entity
│       ├── conversation/              # Conversation entity + CRUD
│       ├── message/                   # Message entity with JSONB columns
│       ├── research/                  # SSE streaming controller + HTTP client to agent
│       └── config/                    # Spring Security + global exception handler
│
├── research-agent/                    # FastAPI service
│   └── src/research_agent/
│       ├── server.py                  # FastAPI app, /research SSE endpoint
│       ├── http_handler.py            # the SSE generator (stream_research)
│       ├── config.py                  # pydantic-settings for env vars
│       ├── agent/
│       │   ├── graph.py               # Deep Agent singleton + LLM wiring
│       │   └── tools.py               # 8 tools, all Redis-cached
│       ├── blocks/
│       │   ├── schemas.py             # pydantic block models
│       │   ├── block_formatter.py     # tool results → typed blocks
│       │   ├── checkpoint_formatter.py# tool name → user-facing string
│       │   └── follow_up_generator.py # OpenAI suggestion generator
│       └── infrastructure/
│           └── redis_client.py        # connect/disconnect + cache_get/set
│
├── docker-compose.yml                 # postgres + redis + agent + backend
└── docs/                              # (this folder)
```

## How the streaming actually flows (concrete example)

```
User: "Bitcoin price in INR"

1. React: POST /api/conversations/abc/query  {query: "Bitcoin price in INR"}
   └─ Authorization: Bearer eyJ…

2. Spring Boot ResearchController:
   ├─ Persist user message to messages table
   ├─ Auto-title the conversation if it's empty
   ├─ Build conversation_history list
   └─ Open SseEmitter, hand request to background executor

3. Spring Boot's executor:
   ├─ HttpClient (HTTP/1.1!) POST http://research-agent:8004/research
   │   └─ Body: {query, conversation_history}
   └─ Read SSE line-by-line, forward each event to SseEmitter

4. Python agent (FastAPI):
   ├─ Build LangChain messages from history + current query
   ├─ async for event in agent.astream_events({"messages": …}, version="v2"):
   │   on_tool_start (get_crypto_price)   → SSE: checkpoint "Fetching bitcoin price..."
   │   on_tool_end                         → SSE: checkpoint "Got crypto data."
   │                                          (also caches result + appends to tool_results)
   │   on_chat_model_end                  → final_text captured
   └─ block_formatter:
       ├─ MarkdownBlock(content=final_text)
       └─ InsightCardsBlock(items from get_crypto_price output)
       → SSE: blocks {data: ResearchResponse}
       → SSE: done

5. Spring Boot:
   ├─ Receive each SSE event from agent → forward to React
   ├─ Parse 'blocks' event → store assistant message + blocks JSONB to Postgres
   └─ Send 'persisted' SSE event with the new message ID

6. React:
   ├─ checkpoint events → animate into CheckpointTrail timeline
   └─ blocks event → BlockRenderer paints markdown + insight cards
```

## Caching layers

- **OpenRouter prompt cache** (ephemeral): system prompt (~2 KB) + tool definitions cached server-side at OpenRouter, ~15% cost saving.
- **Redis tool cache**: every tool wraps its external call with `cache_get(key) → call → cache_set(key, ttl)`. Identical queries within the TTL return instantly with zero LLM/API cost.
- **Browser HTTP cache**: static assets via Vite's content hashing.

## Security posture

- Passwords: bcrypt (Spring's `BCryptPasswordEncoder`, default cost 10).
- Tokens: HS256 JWTs, 24 h expiry, signed with `JWT_SECRET` env var.
- Token storage: `localStorage` (simple). For production, switch to httpOnly cookies + CSRF token.
- CORS: locked to `app.cors.allowed-origins` (default `http://localhost:5173`).
- All `/api/**` routes require Bearer token except `/api/auth/**`.
- `DispatcherType.ASYNC` is permitted to let SSE finish through Spring Security cleanly.

## What's NOT done (intentional, can be added)

- OAuth (Google / GitHub). Foundation is in place; just add a Spring OAuth2 starter and a `social_logins` table.
- Rate limiting. Bucket4j or a Redis sliding-window would slot in before the SSE controller.
- Email verification. Add a `verification_tokens` table + SendGrid/Postmark.
- Multi-tenant / org-level isolation.
- WebSocket as an alternative transport (SSE works fine, WS would be needed only for two-way streaming).

## Verifying everything is wired

```bash
# 1. agent reachable + LLM key configured
curl http://localhost:8004/health/ready
# expect: {"status":"ready","checks":{"redis":"ok","openrouter":"configured", ...}}

# 2. backend reachable
curl http://localhost:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke@x.com","password":"smoketest1","name":"S"}'
# expect: {"token":"eyJ…","id":"…", …}

# 3. end-to-end
# (use the React UI at http://localhost:5173 — register, ask "Bitcoin price in INR")
```
