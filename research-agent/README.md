# Research Agent

FastAPI service that runs a Deep Agents loop with 8 tools and streams results over SSE. Called server-to-server by the backend.

## Setup

```bash
pip install -e ".[test]"
cp .env.example .env
```

## Environment

| Variable | Default | Notes |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8004` | |
| `LOG_LEVEL` | `INFO` | |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173,http://localhost:8080` | comma-separated |
| `MAX_QUERY_CHARS` | `4000` | longer queries get 422 |
| `MAX_HISTORY_MESSAGES` | `20` | |
| `MAX_HISTORY_MESSAGE_CHARS` | `16000` | |
| `REQUEST_TIMEOUT_SECONDS` | `180` | |
| `AGENT_RECURSION_LIMIT` | `40` | |
| `WEBPAGE_MAX_BYTES` | `5242880` | |
| `REDIS_URL` | `redis://localhost:6379` | optional; the cache is skipped when Redis is down |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL` | | primary LLM |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | | fallback LLM |
| `LLM_TEMPERATURE` | `0.3` | |
| `FOLLOW_UP_MODEL` | agent model, or `gpt-4o-mini` on OpenAI | |
| `OCTEN_API_KEY`, `OCTEN_MAX_RESULTS` | | search provider 1 |
| `TAVILY_API_KEY`, `TAVILY_MAX_RESULTS`, `TAVILY_SEARCH_DEPTH` | | search provider 2; DuckDuckGo is the last fallback |
| `JINA_API_KEY` | | optional |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`, `LANGCHAIN_ENDPOINT` | | optional tracing |

## Run

```bash
uvicorn research_agent.server:create_app --factory --port 8004
```

Docker: `docker build -t research-agent .` runs as a non-root user, honors `$PORT`, and has a healthcheck on `/health`.

## Endpoints

- `GET /health`: liveness
- `GET /health/ready`: Redis plus key checks; returns 503 when degraded
- `GET /metrics`: Prometheus
- `POST /research`: `{"query": str, "conversation_history": [{"role": "user"|"assistant", "content": str}]}` returns `text/event-stream`, or 422 when a limit is exceeded

## SSE events

Each stream starts with a `checkpoint` and ends with exactly one `done`.

| Event | Data |
|---|---|
| `checkpoint` | `{status: "in_progress", content, tool?}` |
| `blocks` | `{status: "completed", data: {query, blocks, sources, follow_ups}}` |
| `clarification` | `{status: "completed", content}` |
| `error` | `{status: "failed", content}` (a generic message; details are only logged) |
| `done` | `{status: "completed"\|"failed", metrics}` |

`metrics` is also logged as one JSON line per request (logger `research_agent.metrics`, `event: "research_request"`).

## Tests

```bash
pytest tests
```

The tests mock all external calls and block real network access.
