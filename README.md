# Lumen

Lumen is an autonomous research agent. You ask an open-ended question; the agent plans, picks from 8 tools (web search, page reader, Wikipedia, nearby places, news, stocks, forex, crypto), cross-checks what it finds and streams back a cited answer as typed UI blocks (markdown, data tables, maps, insight cards).

```
React UI ──HTTP+SSE──► FastAPI backend ──HTTP+SSE──► Research agent (FastAPI)
 (Vite/TS)   JWT       + PostgreSQL                  Deep Agents ReAct loop on LangGraph
                                                     ├─ 8 tools ──► Redis tool cache
                                                     └─ LLM: DeepSeek V4.1 Flash via OpenRouter
```

## How the agent works

- **Loop:** `create_deep_agent` (Deep Agents on LangGraph) runs a ReAct loop. The model decides which tools to call, in parallel where it can, and when it has enough to answer.
- **Model:** `deepseek/deepseek-v4.1-flash` through OpenRouter, `max_tokens=4096`. OpenAI `gpt-4o` is used only when no OpenRouter key is configured.
- **Output:** the final text is parsed into typed blocks (`markdown`, `data-table`, `insight-cards`, `leaflet-map`); a second LLM call adds 2–3 follow-up questions.
- **Streaming:** progress is streamed as `checkpoint` events per tool call, followed by one `blocks` event. The answer arrives whole; there is no token-level streaming.

### Tools

| Tool | Source | Cache TTL |
|---|---|---|
| `web_search` | Octen, then Tavily, then DuckDuckGo | 1 h |
| `read_webpage` | Jina Reader, PyMuPDF for PDFs | 6 h |
| `wiki_search` | Wikipedia | 24 h |
| `nearby_places` | Nominatim + Overpass | 24 h |
| `latest_news` | Indian RSS feeds | 15 min |
| `get_stock_price` | yfinance | 15 min |
| `get_forex_rate` | Frankfurter | 1 h |
| `get_crypto_price` | CoinGecko | 5 min |

Results are cached in Redis per tool. Only successful, non-empty results are cached, and a Redis outage never fails a request.

### Guardrails

- **SSRF:** `read_webpage` accepts only public http(s) URLs. It resolves the host, rejects private, loopback, link-local and metadata addresses, connects to the checked IP, re-validates every redirect hop, and caps the download at 5 MB.
- **Limits:** query up to 4000 characters, 20 history messages, a 40-step graph recursion limit and a 180 s request timeout. Exceeding the timeout or step limit returns a clean error.
- **Errors:** exception text is logged server-side only. Clients get one of three fixed messages.
- **Blocking I/O:** synchronous libraries (DuckDuckGo, yfinance, Wikipedia, PyMuPDF, feedparser) run in threads so one slow tool does not stall other requests.

### Observability

Every request ends with a `done` event whose `metrics` payload carries: total latency, time to first checkpoint, per-tool name, latency, cache hit and success, search provider used, LLM call count, input/output tokens (agent and follow-up calls separately), model and outcome. The same data is written as one JSON log line per request (`"event": "research_request"`). Setting `LANGCHAIN_TRACING_V2=true` also sends runs to LangSmith.

## Measured performance

Measured on 2026-10-01 against the full local stack (backend, agent, OpenRouter and live data sources). 28 queries ran one at a time on a cold cache: stocks, forex, crypto, nearby places, news, Wikipedia, multi-step research, page reads and 3 adversarial prompts.

| Metric | Result |
|---|---|
| Completed with an answer | 28 / 28 |
| Latency (p50 / p95 / mean) | 11.7 s / 35.0 s / 14.8 s |
| Time to first progress event (p50) | 1.9 s |
| Cost per query (mean / p95) | $0.0008 / $0.0015 |
| Tool calls per query (mean / p95) | 2.3 / 5.7 |
| Tokens per query (mean in / out) | 14.4k / 0.7k |
| Right tool chosen | 25 / 25 |
| Price answers within 3% of live source | 6 / 6 |
| Cited source URLs that resolve | 94.0 % (12 queries with sources, up to 8 URLs checked each) |
| Answers with 3 follow-up suggestions | 25 / 25 (adversarial prompts excluded) |
| Adversarial prompts leaking data (metadata URL, localhost URL, system prompt) | 0 / 3 |

Cost is computed from the reported token counts at OpenRouter list prices ($0.03 per million input, $0.50 per million output) with no prompt-cache discount, so it is an upper bound. It includes the follow-up call, which averages 616 input and 128 output tokens. Total for the 28 queries: $0.022.

| Category | Queries | Latency p50 | Cost (mean) | Tool calls (mean) |
|---|---|---|---|---|
| stock / forex / crypto | 9 | 5.1-7.5 s | $0.0004 | 1.0 |
| wiki | 2 | 4.9 s | $0.0005 | 1.0 |
| places | 3 | 11.4 s | $0.0008 | 1.7 |
| webpage | 2 | 13.7 s | $0.0011 | 2.5 |
| research | 6 | 18.5 s | $0.0012 | 4.0 |
| news | 3 | 35.6 s | $0.0013 | 5.0 |

**Caching.** On a second pass over the 17 cacheable queries, 17 of 35 tool calls (49 %) were cache hits: stock, forex and wiki 100 %, places 3 of 7, news 6 of 17, crypto 0 of 3 (the 5-minute TTL had expired). A hit returns in about 1 ms against a 1.3 s median for a miss; the slow tools gain most (stock 6.0 s, places 6.8 s, news 4.3 s median on a miss). End-to-end median latency did not change (7.5 s on both passes), because the model calls dominate and the agent takes a different tool path from run to run.

**Concurrency.** 5 simultaneous users all completed (10.8 s wall time). `/health` stayed responsive throughout (p50 9 ms, p95 28 ms, max 38 ms), so tool calls are not blocking the event loop.

**Search providers.** All 29 `web_search` calls were served by Octen. The Tavily and DuckDuckGo fallbacks did not trigger in this run, and no Tavily key was configured.

### Known limits

- News is the slowest category (up to 49.9 s). In an earlier run of the same query set, one news query used 14 tool calls.
- `nearby_places` depends on public Overpass mirrors that are sometimes slow or return 504s. Each call is capped at 35 s and returns a clean error so the agent can fall back to web search. Before that cap, an Overpass outage pushed one query into the 180 s request timeout.
- `latest_news` returned an error for "Latest cricket news" in both the cold and warm passes.
- The sample is 28 queries on one machine, so p95 values rest on very few points.

## Run it

```bash
cp research-agent/.env.example research-agent/.env
export JWT_SECRET="$(openssl rand -hex 32)"
docker compose up --build -d
cd frontend && npm install && npm run dev
```

Set `OPENROUTER_API_KEY` and `OCTEN_API_KEY` in `research-agent/.env`; `TAVILY_API_KEY` and `JINA_API_KEY` are optional. The app is at http://localhost:5173 and the agent at http://localhost:8004.

```bash
cd research-agent && pip install ".[test]" && pytest tests
cd backend && pip install -r requirements.txt -r requirements-dev.txt && pytest tests
```

## Stack

- **Backend:** FastAPI, SQLAlchemy 2 and PostgreSQL. JWT auth, conversation CRUD, and an SSE proxy to the agent that stores each answer.
- **Frontend:** React 18, Vite, TypeScript, Tailwind, zustand and Framer Motion, with a block renderer for the typed answer blocks.
- **Deployment:** EC2 running Docker Compose (Postgres, Redis, agent, backend) and a static frontend on S3 behind CloudFront. GitHub Actions runs tests and deploys through OIDC and SSM.
