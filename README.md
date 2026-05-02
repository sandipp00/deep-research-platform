# Lumen — Deep Research Platform

A full-stack research assistant: React frontend, Spring Boot (Java 21) backend, PostgreSQL persistence, and a Python research agent that runs a Deep Agents ReAct loop with 8 custom tools and streams structured rich-media blocks (markdown, tables, maps, charts, insight cards) over SSE.

```
┌──────────────┐  HTTP+SSE   ┌────────────────────┐   HTTP+SSE   ┌────────────────────┐
│  React UI    │◄───────────►│  Spring Boot API   │◄────────────►│ Python Research    │
│  (Vite/TS)   │  JWT auth   │  + PostgreSQL      │              │ Agent (FastAPI)    │
└──────────────┘             └────────────────────┘              └────────────────────┘
                                       │                                    │
                                       ▼                                    ▼
                                 PostgreSQL 16                          Redis 7
                              (users, conversations,                    (tool cache)
                               messages, blocks)
```

## Quick start

```bash
# 1. add API keys to the agent
cp research-agent/.env.example research-agent/.env
# fill in OPENROUTER_API_KEY and EXA_API_KEY (TAVILY_API_KEY recommended)

# 2. (optional) override JWT secret in your shell
export JWT_SECRET="$(openssl rand -base64 48)"

# 3. boot postgres + redis + agent + backend
docker compose up --build -d

# 4. run the frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 → register → ask anything.

> **Port note:** Postgres is mapped to host `5433` (not 5432) to avoid clashing with a local Postgres install. Inside the docker network the service is still on 5432.

## What's where

| Path | What |
|---|---|
| `frontend/` | React 18 + Vite + TypeScript + Tailwind + Framer Motion. Modular `BlockRenderer` adapts to every research block type (markdown, data-table, leaflet-map, insight-cards) with a JSON fallback so unknown future block types never break the UI. |
| `backend/` | Spring Boot 3.3, Java 21. JWT auth (register/login/me), conversations CRUD, persistent messages with JSONB blocks. `POST /api/conversations/{id}/query` streams SSE from the Python agent and writes the final assistant message + blocks to Postgres. |
| `research-agent/` | FastAPI service (port 8004). `POST /research` returns SSE: `checkpoint` per tool call, then `blocks` (or `clarification`/`error`), then `done`. Deep Agents ReAct loop, Redis-cached tool results, OpenRouter primary + OpenAI fallback. |
| `docker-compose.yml` | postgres, redis, research-agent, backend. Frontend runs natively for HMR. |

## API surface (backend)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | `{email, password, name}` → `{token, ...}` |
| POST | `/api/auth/login` | — | `{email, password}` → `{token, ...}` |
| GET  | `/api/auth/me` | Bearer | Current user |
| GET  | `/api/conversations` | Bearer | List user's conversations |
| POST | `/api/conversations` | Bearer | Create empty conversation |
| GET  | `/api/conversations/{id}` | Bearer | One conversation |
| PATCH| `/api/conversations/{id}` | Bearer | Rename — `{title}` |
| DELETE | `/api/conversations/{id}` | Bearer | Delete |
| GET  | `/api/conversations/{id}/messages` | Bearer | Full transcript with blocks |
| POST | `/api/conversations/{id}/query` | Bearer | `{query}` → SSE stream |

### SSE event types from `/query`

| Event | Payload | When |
|---|---|---|
| `user_message` | `{id, createdAt}` | Right after the user message is persisted |
| `checkpoint` | `{status, content, tool?}` | Per tool call from the agent |
| `blocks` | `{status, data: ResearchResponse}` | Final assembled blocks (terminal) |
| `clarification` | `{status, content}` | Agent needs more info (terminal) |
| `error` | `{status, content}` | Failure (terminal) |
| `persisted` | `{messageId}` | Backend has stored the assistant message |

## Database

Auto-created on first run via `spring.jpa.hibernate.ddl-auto=update`. Schema:

- `users(id UUID, email, password_hash, name, created_at)`
- `conversations(id UUID, user_id, title, created_at, updated_at)`
- `messages(id UUID, conversation_id, role, content, blocks JSONB, sources JSONB, follow_ups JSONB, created_at)`

## Adding a new block type

1. Add the schema in `research-agent/src/research_agent/blocks/schemas.py` and emit it from `block_formatter.py`.
2. Mirror the type in `frontend/src/types.ts`.
3. Drop a new component in `frontend/src/components/blocks/<Name>Block.tsx`.
4. Wire it into the switch in `BlockRenderer.tsx`.

Until step 4, the new block type renders via `FallbackBlock` (JSON viewer) — so the UI never breaks on unknown blocks.

## Security notes

- JWT secret is `JWT_SECRET` env var (set a long random one in prod).
- Auth gate covers `/api/**` except `/api/auth/**`.
- The frontend stores the JWT in `localStorage` for simplicity. For prod consider HTTP-only cookies + CSRF.
- CORS is restricted to `app.cors.allowed-origins` (default `http://localhost:5173`).

## Development tips

- Backend logs: `docker compose logs -f backend`
- Agent logs:   `docker compose logs -f research-agent`
- Reset DB:     `docker compose down -v && docker compose up -d`
- Health:       `curl http://localhost:8004/health/ready`  (agent), `curl http://localhost:8080/health` (backend; through Spring Boot Actuator if added)
