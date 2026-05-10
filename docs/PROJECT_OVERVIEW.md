# Lumen — Project Overview

A full-stack AI research assistant. Three services, all containerised, talking over HTTP+SSE.

```
┌──────────────┐  HTTP+SSE   ┌──────────────────┐  HTTP+SSE   ┌─────────────────────┐
│  React UI    │◄──────────► │ FastAPI Backend  │◄──────────► │ Python Research     │
│  (Vite/TS)   │   JWT       │ + PostgreSQL     │             │ Agent (FastAPI)     │
└──────────────┘             └──────────────────┘             └─────────────────────┘
                                      │                                    │
                                      ▼                                    ▼
                                Postgres 16                            Redis 7
                            (users, conversations,                 (per-tool result
                             messages, blocks JSONB)                cache, TTL'd)
```

## Tech stack

### Frontend
| Tech | Why |
|---|---|
| **React 18 + TypeScript** | Strong typing across the block system (server emits typed Pydantic, client renders typed components) |
| **Vite** | Sub-second HMR |
| **Tailwind CSS + Framer Motion** | Design tokens (violet → pink → cyan), micro-interactions |
| **Zustand** | Tiny global store (`auth`, `chat`) — no Redux ceremony for a 2-store app |
| **React Router 6** | `/login`, `/register`, `/c/:id` |
| **`@microsoft/fetch-event-source`** | Browser `EventSource` can't send `Authorization` headers; this client can |
| **react-leaflet** | Maps with custom on-brand SVG pins; tile pane is dark-filtered via CSS |

### Backend
| Tech | Why |
|---|---|
| **FastAPI 0.115 / Python 3.12** | Same language as the agent; Pydantic validation; auto-generated OpenAPI |
| **SQLAlchemy 2** | Mature ORM with `Mapped[...]` typing |
| **PostgreSQL 16** | JSONB lets each message store an arbitrary array of typed blocks without polymorphic tables |
| **`python-jose`** | JWT (HS256, 24h) — stateless, no Redis session store needed |
| **`passlib[bcrypt]`** | Bcrypt password hashing |
| **`httpx`** | Async streaming HTTP client for the agent SSE bridge |
| **uvicorn** | ASGI server |

### Research Agent
| Tech | Why |
|---|---|
| **Deep Agents (LangGraph)** | Autonomous ReAct loop with planning + reflection |
| **Claude Sonnet via OpenRouter** | Best price/quality at our scale; ephemeral prompt caching for system prompt + tool schemas |
| **OpenAI fallback** | Continuity if OpenRouter is degraded |
| **Redis 7** | Per-tool result cache (TTLs: news 15m, prices 5m, places 24h, web 1h) |
| **Exa + Tavily + DDG fallback chain** | Search resilience |
| **Jina Reader + PyMuPDF** | Webpage and PDF reading |

## Database schema

```sql
users(id UUID pk, email unique, password_hash, name, created_at)
conversations(id UUID pk, user_id fk, title, created_at, updated_at)
messages(
  id UUID pk, conversation_id fk, role varchar(16),
  content text, blocks jsonb, sources jsonb, follow_ups jsonb,
  created_at
)
```

Tables auto-create on backend startup via `Base.metadata.create_all`. Production would add Alembic migrations.

## API surface

```
POST   /api/auth/register          { email, password, name } → { token, id, email, name }
POST   /api/auth/login             { email, password }       → { token, id, email, name }
GET    /api/auth/me                                          → { id, email, name }

GET    /api/conversations                                    → [Conversation]
POST   /api/conversations          { title? }                → Conversation
GET    /api/conversations/{id}                               → Conversation
PATCH  /api/conversations/{id}     { title }                 → 204
DELETE /api/conversations/{id}                               → 204
GET    /api/conversations/{id}/messages                      → [Message]

POST   /api/conversations/{id}/query   { query }             → SSE stream
```

## Block system

The interesting part. The agent emits a typed array of "blocks" that the frontend renders as a switch:

```ts
type Block =
  | { template_id: "markdown";       data: { content: string } }
  | { template_id: "data-table";     data: { columns, rows } }
  | { template_id: "insight-cards";  data: { items: [{title, body, severity}] } }
  | { template_id: "leaflet-map";    data: { center, zoom, markers } }
  | { template_id: string;           data: unknown };  // fallback
```

Same shape, three places: Pydantic models in `research-agent/`, JSONB column in `messages.blocks`, TypeScript types + `BlockRenderer` switch in `frontend/`. Unknown `template_id` → `FallbackBlock` (collapsible JSON), so server-side new blocks can ship without a frontend deploy.

## Streaming flow ("Bitcoin price in INR")

```
1. Frontend POST /api/conversations/{id}/query  (Bearer JWT)

2. Backend (FastAPI):
   - persists user message
   - opens async httpx stream to research-agent /research
   - emits SSE event "user_message" with persisted id

3. Agent (Deep Agents loop):
   - LLM picks get_crypto_price
   - Tool runs (Redis cache hit / CoinGecko miss)
   - Backend forwards "checkpoint" SSE
   - LLM composes reply, formatter emits insight-cards + markdown blocks
   - Backend forwards "blocks" SSE

4. Backend:
   - persists assistant message + blocks (JSONB)
   - emits "persisted" SSE with messageId
   - closes stream
```

## Caching

- **OpenRouter prompt cache** (ephemeral): system prompt + tool schemas don't re-tokenize every turn
- **Redis tool cache**: per-tool key (hash of input) with TTL — cheap requeries, instant for repeat questions
- **Browser HTTP cache**: standard for static assets

## Security

- Passwords: bcrypt via passlib
- JWT: HS256, 24h, claims `{sub: email, uid, name}`
- CORS: `CORS_ALLOWED_ORIGINS` env var (default `http://localhost:5173`)
- Auth: every `/api/conversations*` route requires Bearer token; `/api/auth/**` is open
- Bearer accepted via `Authorization` header or `?token=` query param (latter is for SSE clients that can't set headers)

## Repo layout

```
deep-research-platform/
├── frontend/                          # React + Vite + TS
│   └── src/
│       ├── components/blocks/         # one per block type + FallbackBlock
│       ├── components/                # ChatPanel, Sidebar, ChatInput, CheckpointTrail, MessageBubble
│       ├── pages/                     # Login, Register, Chat
│       ├── store/                     # zustand: auth.ts, chat.ts
│       └── lib/                       # axios + SSE helpers
├── backend/                           # FastAPI + SQLAlchemy + JWT
│   └── app/
│       ├── routers/                   # auth.py, conversations.py, research.py (SSE bridge)
│       ├── models.py                  # SQLAlchemy User, Conversation, Message
│       ├── schemas.py                 # Pydantic request/response (camelCase aliased)
│       ├── security.py                # bcrypt + JWT
│       ├── deps.py                    # get_current_user
│       ├── research_client.py         # httpx async SSE consumer
│       ├── db.py, config.py, main.py
├── research-agent/                    # FastAPI + Deep Agents
│   └── src/research_agent/
│       ├── agent/                     # graph.py, tools.py
│       ├── blocks/                    # schemas.py, block_formatter.py
│       └── server.py, http_handler.py
└── docker-compose.yml                 # postgres, redis, research-agent, backend
```

## Future work

- Alembic migrations
- httpOnly cookie auth instead of `localStorage`
- Tool-choice transparency in the UI (show which search provider answered)
- Streaming follow-up generation (currently a separate trailing LLM call)
- WebSocket for bidirectional control (stop / mid-stream feedback)
