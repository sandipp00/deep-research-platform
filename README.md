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
- **Grounding:** the system prompt requires a search or Wikipedia call before answering any factual or research question, so answers come from tool results rather than model memory.
- **Output:** the final text is parsed into typed blocks (`markdown`, `data-table`, `insight-cards`, `leaflet-map`); a second LLM call adds 2–3 follow-up questions.
- **Streaming:** progress is streamed as `checkpoint` events per tool call, followed by one `blocks` event. The answer arrives whole; there is no token-level streaming.

### Tools

| Tool | Source | Cache TTL |
|---|---|---|
| `web_search` | Octen, then Tavily, then DuckDuckGo | 1 h |
| `read_webpage` | Jina Reader, PyMuPDF for PDFs | 6 h |
| `wiki_search` | Wikipedia | 24 h |
| `nearby_places` | Nominatim + Overpass (all mirrors queried in parallel) | 24 h |
| `latest_news` | Indian RSS feeds, Google News search as fallback | 15 min |
| `get_stock_price` | Yahoo Finance chart API (P/E best-effort via yfinance) | 15 min |
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

Measured on 2026-10-08 against the full local stack (backend, agent, OpenRouter and live data sources). 28 queries ran one at a time on a cold cache: stocks, forex, crypto, nearby places, news, Wikipedia, multi-step research, page reads and 3 adversarial prompts.

| Metric | Result |
|---|---|
| Completed with an answer | 28 / 28 |
| Latency (p50 / p95 / mean) | 8.6 s / 18.6 s / 9.5 s |
| Time to first progress event (p50) | 2.0 s |
| Cost per query (mean / p95) | $0.0007 / $0.0012 |
| Tool calls per query (mean / p95) | 1.6 / 4.0 |
| Tokens per query (mean in / out) | 12.0k / 0.7k |
| Right tool chosen | 25 / 25 |
| Answers given without calling any tool (adversarial prompts excluded) | 0 / 25 |
| Stock and crypto prices within 3% of live source | 5 / 5 |
| Cited source URLs that resolve | 98 % (10 queries with sources, up to 8 URLs checked each) |
| Answers with 3 follow-up suggestions | 25 / 25 |
| Adversarial prompts leaking data (metadata URL, localhost URL, system prompt) | 0 / 3 |

Cost is computed from the reported token counts at OpenRouter list prices ($0.03 per million input, $0.50 per million output) with no prompt-cache discount, so it is an upper bound. It includes the follow-up call. Total for the 28 queries: $0.020.

| Category | Queries | Latency p50 | Cost (mean) | Tool calls (mean) |
|---|---|---|---|---|
| stock / forex / crypto | 9 | 5.5-9.2 s | $0.0004-0.0007 | 1.0-1.3 |
| wiki | 2 | 8.4 s | $0.0005 | 1.0 |
| places | 3 | 8.5 s | $0.0009 | 2.0 |
| webpage | 2 | 11.5 s | $0.0007 | 1.0 |
| research | 6 | 10.1 s | $0.0010 | 3.0 |
| news | 3 | 11.7 s | $0.0009 | 2.3 |

**Caching.** On a second pass over the 17 cacheable queries, 18 of 24 tool calls (75 %) were cache hits: stock, forex, crypto and wiki 100 %, news 6 of 7, places 1 of 6 (the agent words its place and type arguments differently from run to run, so the keys differ). A hit returns in about 1 ms against a 1.1 s median for a miss, and median latency over those queries fell from 8.5 s cold to 5.8 s warm.

**Concurrency.** 5 simultaneous users all completed (9.4 s wall time, per-request p95 7.6 s). `/health` stayed responsive throughout (p50 11 ms, p95 96 ms, max 390 ms), so tool calls are not blocking the event loop.

**Search providers.** All 14 `web_search` calls were served by Octen. The Tavily and DuckDuckGo fallbacks did not trigger in this run, and no Tavily key was configured.

**Grounding check.** An earlier run showed the agent answering research questions from memory with no search and no sources. On three such queries repeated 18 times each, that happened in 10 of 18 runs with a bare rename of the persona, 6 of 18 with the original prompt and 0 of 18 once the grounding rule was added.

### Known limits

- `nearby_places` depends on public Overpass mirrors that are sometimes slow or return 504s. Calls are capped at 35 s and return a clean error so the agent can fall back to web search. In an earlier run during an outage, places queries took a median of 46 s.
- The price check covers stocks and crypto only. The reference source for forex could not be queried by my checker, and one crypto reference lookup failed.
- Stock P/E is fetched best-effort for up to 1 s and is left out of the card when it is not ready.
- Stock, forex, crypto and Wikipedia answers carry no source URLs, so only 10 of 25 answers have citations.
- The tool path varies from run to run, so latency and tool-call counts on open-ended queries are noisy. The sample is 28 queries on one machine, so p95 values rest on very few points.

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
