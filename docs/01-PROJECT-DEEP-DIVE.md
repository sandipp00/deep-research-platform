# Lumen — Project Deep Dive

This doc walks through Lumen end-to-end, following a single user's journey from landing page to answer, and explains **every library in the stack and why it's there**. Read this before touching code — [`02-DOCKER-CICD.md`](./02-DOCKER-CICD.md) and [`03-AWS-DEPLOYMENT.md`](./03-AWS-DEPLOYMENT.md) build on it.

## The three services

```
┌──────────────┐  HTTP+SSE   ┌────────────────────┐   HTTP+SSE   ┌────────────────────┐
│  React UI    │◄───────────►│  FastAPI Backend   │◄────────────►│ Python Research    │
│  (Vite/TS)   │  JWT auth   │  + PostgreSQL      │              │ Agent (FastAPI)    │
└──────────────┘             └────────────────────┘              └────────────────────┘
                                       │                                    │
                                       ▼                                    ▼
                                 PostgreSQL 16                          Redis 7
                              (users, conversations,                    (tool cache)
                               messages, blocks)
```

- **`frontend/`** — the only thing a browser talks to. Static React app, no server-side rendering.
- **`backend/`** — the system of record. Owns auth, conversations, and message history in Postgres. Proxies research requests to the agent and persists the results.
- **`research-agent/`** — the "brain." A stateless FastAPI service that runs one LangGraph ReAct loop per query, calls out to 8 tools, and streams progress + a final structured answer back over SSE. It never touches Postgres — Redis is its only state, and only as a cache.

The backend and the research-agent are deliberately separate deployables: the agent is CPU/network-bound and stateless (easy to scale horizontally, easy to swap models), while the backend is I/O-bound against Postgres and owns durable state. Scaling and redeploying one never touches the other.

---

## User flow, step by step

### 1. Landing → sign-up

A visitor hits `/` and gets `frontend/src/pages/Landing.tsx` — a public marketing page (light/dark toggle, feature grid, no auth required). Clicking **Get started** routes to `/register`.

`Register.tsx` calls `useAuth().register(email, password, name)` (Zustand store, `src/store/auth.ts`), which does:

```
POST /api/auth/register  { email, password, name }
```

On the backend, `backend/app/routers/auth.py`:
- hashes the password with **`passlib[bcrypt]`** (`security.py::hash_password`) — never stores plaintext
- inserts a `User` row via **SQLAlchemy 2.0** (`models.py`)
- issues a JWT with **`python-jose`** (`security.py::issue_token`) — `HS256`, signed with `JWT_SECRET`, `sub`/`uid`/`name` claims, expires per `JWT_EXPIRATION_MINUTES`

The frontend stores `{token, id, email, name}` in `localStorage` and redirects to `/app`.

**Why bcrypt + JWT and not sessions?** Both services (backend, agent) are stateless HTTP services behind a load balancer in the target deployment — a bearer token needs no shared session store. `passlib` abstracts the bcrypt work factor so it can be tuned without touching call sites.

### 2. Authenticated shell

`/app` is a protected route (`App.tsx::Protected` — redirects to `/login` if `useAuth().user` is null). It renders `pages/Chat.tsx`, which composes `ConversationSidebar` + the active conversation panel.

On mount, the sidebar calls `GET /api/conversations` (Bearer auth) to list the user's conversations, each scoped by `Conversation.user_id` — the backend never returns another user's rows (`_owned()` helper in `routers/research.py` and equivalent checks in `routers/conversations.py`).

### 3. Asking a question

Typing a query and hitting send calls `useChat().sendQuery(...)` → `postSse("/conversations/{id}/query", {query}, handlers)` in `frontend/src/lib/sse.ts`. This uses **`@microsoft/fetch-event-source`** instead of the native `EventSource` API specifically because native `EventSource` can't send a `POST` body or an `Authorization` header — both required here.

On the backend, `routers/research.py::query_conversation`:
1. Persists the user's message immediately (`Message(role=USER, content=...)`) and, if this is the first message, derives a conversation title from it.
2. Loads the full prior transcript for this conversation (for multi-turn context).
3. Opens a `StreamingResponse` generator that calls `research_client.py::stream_research(query, history)`.

`research_client.py` is a thin **`httpx`** async streaming client that `POST`s to the research-agent's `/research` endpoint and re-parses raw `event:`/`data:` SSE frames into `AgentEvent` objects — the backend is a pass-through proxy, not a re-implementation of the agent's protocol.

As events arrive, the backend **re-emits them to the browser unchanged** (so the frontend gets checkpoints in near-real-time) while also accumulating the final `blocks`/`sources`/`follow_ups`/`clarification`/`error` payload. Once the agent's stream ends, it persists the assistant's `Message` row in a **fresh** SQLAlchemy session (`with SessionLocal() as persist_db`) — deliberately not the request-scoped session, since by then the original request's session may already be torn down — and emits a final `persisted` event with the new message ID.

### 4. Inside the research agent

`research-agent/src/research_agent/server.py` exposes `POST /research`. `http_handler.py::stream_research`:

1. Emits an initial `checkpoint` ("Researching your query...").
2. Calls `agent/graph.py::get_agent()` — a **lazily-initialized singleton** behind an `asyncio.Lock`, so the (relatively expensive) agent graph is built once per process, not once per request.
3. Streams the agent's execution via **`agent.astream_events(..., version="v2")`** — LangGraph's event stream API — translating `on_tool_start`/`on_tool_end`/`on_chat_model_end` into `checkpoint` SSE frames the frontend renders as a live "thinking" trail (`CheckpointTrail.tsx`).
4. Once the model's final turn completes, if the response starts with the literal string `[CLARIFICATION]`, it's treated as a follow-up question and streamed as a `clarification` event (terminal — no blocks). Otherwise the raw text + collected tool outputs go through `blocks/block_formatter.py::format_blocks`, which turns tool results into typed UI blocks (see below), then generates follow-up suggestions (`blocks/follow_up_generator.py`, 3s timeout, best-effort) and emits a `blocks` event.
5. Always ends with a `done` event.

#### The agent itself: Deep Agents + LangGraph

`get_agent()` calls **`deepagents.create_deep_agent(model, system_prompt, tools)`**. `deepagents` is a small framework on top of **LangGraph** that gives a plain ReAct tool-calling loop a few extra capabilities out of the box — most relevantly a `write_todos` planning tool the system prompt tells the model to use for multi-step research, so the loop can plan → execute → replan instead of single-shot tool calling. The compiled graph is a `CompiledStateGraph` (LangGraph's execution unit); `astream_events` is how you observe every node transition inside it without waiting for the whole run to finish.

The model itself is built by `_build_model()` using **`langchain_openai.ChatOpenAI`** pointed at a non-OpenAI base URL — this works because **OpenRouter exposes an OpenAI-compatible `/chat/completions` API**, so the same LangChain client class works for OpenRouter, and for the OpenAI fallback, just by swapping `base_url`/`api_key`/`model`. Primary model is `deepseek/deepseek-v4.1-flash` (see [README performance table](../README.md#performance--cost) for why); `model_kwargs.extra_body.cache_control: {type: ephemeral}` turns on prompt caching so the (long) system prompt + tool schemas aren't re-billed on every turn. If `OPENROUTER_API_KEY` is unset, it falls back to plain OpenAI (`gpt-4o` by default).

#### The 8 tools (`agent/tools.py`)

Every tool is Redis-cached with its own TTL via a shared `_cached(key, ttl, fetch_fn)` helper — cheap, short-TTL data (crypto: 5 min) vs. slow-changing data (Wikipedia: 24h) get different cache lifetimes:

| Tool | Purpose | Provider chain | Cache TTL |
|---|---|---|---|
| `web_search` | General search | **Octen** → Tavily → DuckDuckGo | 1h |
| `read_webpage` | Full page/PDF text | Jina Reader → PyMuPDF (PDF fallback) | 6h |
| `wiki_search` | Definitions/facts | `wikipedia-api` + `wikipedia` | 24h |
| `nearby_places` | Geo search | Nominatim (geocode) + OSM Overpass | 24h |
| `latest_news` | Breaking news | RSS (NDTV, ET, Moneycontrol, ToI) via `feedparser` | 15 min |
| `get_stock_price` | Equities | `yfinance` | 5 min |
| `get_forex_rate` | FX | Frankfurter API | 1h |
| `get_crypto_price` | Crypto | CoinGecko API | 5 min |

**Why Octen for web search:** it's a search API purpose-built for LLM/agent consumption — structured JSON results with an LLM-ready `highlight` field, sub-second latency for a single query (see the [Octen API reference](https://docs.octen.ai/api-reference/broad-search)), and a `broad_search` mode that fans a query out into sub-queries server-side if Lumen ever needs deeper multi-angle research than the single-`search` call it uses today. The provider chain (Octen → Tavily → DuckDuckGo) means a single vendor outage degrades search quality, not availability — `web_search` still returns *something*.

Each `@tool`-decorated function is a plain async Python function; LangChain's `tool` decorator introspects the docstring and type hints to build the JSON schema the model sees, so the docstrings above the `def` aren't just comments — they're the tool's contract with the LLM (what it does, when to use it, argument meanings).

#### Turning tool output into UI (`blocks/`)

`block_formatter.py::format_blocks` is a deterministic (non-LLM) pass over the raw tool outputs and final text:

1. The model's final answer always becomes a `markdown` block.
2. `nearby_places` output (a pipe-delimited `PLACE|name|lat|lon|address|dist` format, see `tools.py`) is parsed into a `leaflet-map` block (markers) + a `data-table` block (rows).
3. Financial tool output (`STOCK|...`, `FOREX|...`, `CRYPTO|...` structured lines) becomes `insight-cards` — with a markdown-table fallback parser in case the model routes a price query through `web_search` anyway despite the prompt telling it not to (defensive, not the happy path).

`schemas.py` (Pydantic) defines every block's shape; the frontend's `BlockRenderer.tsx` switches on `template_id` and falls back to a raw JSON viewer (`FallbackBlock`) for any block type it doesn't recognize yet — so adding a 5th block type never breaks old clients mid-rollout. See the README's "Adding a new block type" section for the 4-step recipe.

### 5. Rendering the stream (frontend)

`ChatPanel.tsx` / `CheckpointTrail.tsx` subscribe to the SSE handlers from `useChat`. Each `checkpoint` event appends a line to a live "thinking" trail (with the specific tool name, formatted by `checkpoint_formatter.py` into a human sentence like "Searching the web for..."). A terminal `blocks` event replaces the trail with the final `MessageBubble`, which hands each block off to `BlockRenderer`. **`framer-motion`** drives the enter/exit animations; **`react-markdown` + `remark-gfm`** render the markdown block (tables, etc.); **`react-leaflet`** renders the map block; **`zustand`** (`store/chat.ts`) holds conversation/message state without a Context re-render cascade.

### 6. Persistence model

Postgres schema (auto-created on backend startup via `Base.metadata.create_all` — no migration tool wired up yet, see gap below):

```sql
users(id UUID pk, email unique, password_hash, name, created_at)
conversations(id UUID pk, user_id fk→users, title, created_at, updated_at)
messages(id UUID pk, conversation_id fk→conversations, role, content,
         blocks JSONB, sources JSONB, follow_ups JSONB, created_at)
```

`blocks`/`sources`/`follow_ups` are stored as **JSONB**, not normalized tables — block shapes evolve fast (see block-type recipe above) and are never queried by their internal fields, only fetched whole and handed to the frontend. JSONB avoids a migration for every new block field while still being indexable if that's ever needed.

`alembic` is in `backend/requirements.txt` but not yet wired up — `create_all` is fine for a portfolio project bootstrapping fresh, but is a real gap once there's production data to migrate around (tracked in the AWS deployment doc's gaps section).

---

## Full library reference

### `frontend/`

| Library | Role |
|---|---|
| **React 18 + Vite + TypeScript** | UI runtime, dev server/bundler, type safety |
| **Tailwind CSS** | Utility-first styling; `darkMode: "class"` powers the light/dark toggle |
| **Framer Motion** | Enter/exit animations across the chat trail, landing page sections, message bubbles |
| **Zustand** | Minimal global state (`auth`, `chat`, `theme` stores) — no Redux boilerplate, no Context re-render fan-out |
| **React Router** | Client-side routing (`/`, `/login`, `/register`, `/app`, `/app/c/:id`) |
| **axios** | REST calls (`/api/auth/*`, `/api/conversations*`) with a request interceptor that attaches the JWT and a response interceptor that force-logs-out on 401 |
| **`@microsoft/fetch-event-source`** | POST-capable, header-capable SSE client (native `EventSource` supports neither) |
| **react-leaflet + Leaflet** | Interactive maps for `nearby_places` results |
| **react-markdown + remark-gfm** | Renders the agent's markdown block, including GFM tables |
| **lucide-react** | Icon set used throughout (landing page, sidebar, buttons) |
| **clsx** | Conditional className composition |

### `backend/`

| Library | Role |
|---|---|
| **FastAPI** | Async web framework, request validation via Pydantic models, `StreamingResponse` for SSE |
| **Uvicorn (`[standard]`)** | ASGI server; `--proxy-headers` so it trusts `X-Forwarded-*` from a reverse proxy/load balancer |
| **SQLAlchemy 2.0** | ORM — declarative `Mapped[...]` models, session management |
| **psycopg[binary]** | Postgres driver (psycopg3), used via `postgresql+psycopg://` DSN |
| **Alembic** | Migration tool — installed, not yet wired up (see gap above) |
| **Pydantic + pydantic-settings** | Request/response schemas; `Settings` reads `.env` |
| **python-jose[cryptography]** | JWT encode/decode (HS256) |
| **passlib[bcrypt] + bcrypt** | Password hashing |
| **httpx** | Async HTTP client used to stream from the research-agent |
| **email-validator** | Validates the `email` field on register/login schemas |

### `research-agent/`

| Library | Role |
|---|---|
| **FastAPI + Uvicorn** | Same role as backend, separate process |
| **LangChain (`langchain-core`, `langchain-openai`, `langchain`)** | `ChatOpenAI` client, `@tool` decorator, message types |
| **LangGraph** | Underlying graph execution engine `deepagents` builds on; `astream_events` for live progress |
| **deepagents** | ReAct loop + planning (`write_todos`) on top of LangGraph |
| **redis (async client)** | Per-tool result cache, keyed by a SHA-256 hash of the tool's arguments |
| **httpx** | Outbound calls to Octen, Tavily, Jina, Nominatim, Overpass, Frankfurter, CoinGecko, RSS feeds |
| **octen** | Primary web search provider SDK |
| **duckduckgo-search** | Last-resort search fallback (no API key required) |
| **yfinance** | Stock price/fundamentals lookup |
| **feedparser** | RSS parsing for `latest_news` |
| **wikipedia-api** | Wikipedia summaries for `wiki_search` |
| **pymupdf (`fitz`)** | PDF text extraction fallback for `read_webpage` |
| **prometheus-fastapi-instrumentator** | Exposes `/metrics` for scraping |
| **coloredlogs** | Readable local dev logs |

---

## Known gaps (by design, per project scope)

Carried over from earlier scoping decisions — intentionally out of scope for this portfolio project, not oversights: rate limiting, email verification, org/multi-tenant isolation, JWT revocation list, and Alembic migrations wired to `create_all`. See [`03-AWS-DEPLOYMENT.md`](./03-AWS-DEPLOYMENT.md) for which of these matter once this leaves a single developer's laptop.
