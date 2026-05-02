# Interview Prep — Lumen / Deep Research Platform

A deep dive on what to say, what they'll ask, and how to talk about it confidently. Use this together with `PROJECT_OVERVIEW.md` (technical reference) and `AI_LEARNING_ROADMAP.md` (for AI-shift questions).

---

## The 30-second pitch

> "Lumen is an AI research assistant I built end-to-end. Users ask questions in any language, an autonomous agent picks the right tools — web search, OpenStreetMap, finance APIs, news feeds — and runs a multi-step ReAct loop. The frontend streams progress over Server-Sent Events and renders the answer as adaptive UI blocks: markdown summaries, sortable tables, interactive maps, severity-colored insight cards. Three services, three languages: React + TypeScript frontend, Spring Boot + PostgreSQL backend, FastAPI + Deep Agents Python service. Everything runs in Docker."

Practice it until you can say it without thinking.

## The 3-minute version

> "The platform sits on three tiers. The **frontend** is React 18 with TypeScript and Tailwind — the centerpiece is a `BlockRenderer` that dispatches each agent response to a typed component: maps, tables, cards, markdown. Anything unknown falls through to a JSON viewer so the UI never breaks when the agent invents a new block.
>
> The **backend** is Spring Boot 3 on Java 21. It owns auth — register/login with JWT and bcrypt — plus persistence and the streaming bridge. When you ask a question it persists the message, opens an SSE connection to the Python agent, forwards every event to the browser, and writes the final assistant message with its blocks as JSONB into Postgres.
>
> The **agent** is FastAPI plus the Deep Agents framework — a middleware-based ReAct loop on top of LangGraph. It has eight custom tools — Exa for web search, OpenStreetMap Overpass for nearby places, yfinance, CoinGecko, RSS feeds, Wikipedia, Jina Reader for webpages — all Redis-cached with per-tool TTLs. The LLM is Claude Sonnet via OpenRouter with prompt caching, OpenAI as fallback.
>
> The whole thing is one `docker compose up`. The hardest bug was a Java HttpClient/uvicorn HTTP/2 mismatch that silently dropped the request body — fixed by forcing HTTP/1.1. The most fun part was making the UI adaptive: schemas in Pydantic on the agent side, mirrored TypeScript types on the frontend, a switch statement in the renderer."

## Architectural decisions (you'll be asked "why X over Y")

### 1. Why three services instead of a monolith?

**Decision:** separate Python agent, Java backend, React frontend.

**Why:**
- **Language fit**: Python has the LLM ecosystem (LangChain, Deep Agents, Pydantic, half of HuggingFace). Java has the enterprise stack (Spring, JPA, Spring Security). React owns the browser.
- **Failure isolation**: agent OOM doesn't take down auth.
- **Independent scaling**: agent runs are LLM-bound (slow), auth is fast — different scaling profiles.
- **Hiring**: easier to find a Java backend person + a Python ML person separately than one polyglot.

**Tradeoff:** more moving parts, two deploy pipelines, network hops between services.

### 2. Why SSE and not WebSocket?

**Decision:** Server-Sent Events for streaming.

**Why:**
- Communication is one-way (server → client). WS adds protocol overhead we don't need.
- SSE is plain HTTP — passes through firewalls, CDNs, proxies that block WS.
- Auto-reconnect is built into the spec.
- Easier to debug — `curl -N` shows the stream live.

**Tradeoff:** browsers cap concurrent SSE per origin to ~6. If users open many tabs simultaneously they'd hit the limit. Not a real problem for a single-tab app.

### 3. Why JSONB for the blocks column?

**Decision:** `blocks JSONB` instead of a separate `blocks` table.

**Why:**
- Blocks are heterogeneous — a markdown block has `{content}`, a leaflet-map has `{center, zoom, markers[]}`, an insight-card has `{items[{title,body,severity}]}`. Modeling each as a row would mean polymorphic associations or N tables.
- JSONB is queryable: `WHERE blocks @> '[{"template_id":"leaflet-map"}]'` finds all messages containing maps.
- Postgres GIN indexes work on JSONB.
- Deserializes naturally to React's heterogeneous block array.

**Tradeoff:** can't add a foreign key from a block to another table. Acceptable — blocks are leaf data.

### 4. Why JWT and not session cookies?

**Decision:** stateless JWT in `Authorization: Bearer …`.

**Why:**
- Backend is stateless; no Redis-backed session store.
- Frontend talks to the backend over CORS in dev, JWT is simpler than CSRF tokens for that.
- Auth claims (user id, name) ride in the token — no DB hit on every request.

**Tradeoff:** can't revoke a JWT mid-flight without a denylist. We chose 24-hour expiry as the tradeoff. If we needed instant revocation we'd add a Redis denylist.

### 5. Why BlockRenderer as a switch and not a registry pattern?

**Decision:** plain `switch (template_id)`.

**Why:**
- Five block types. A registry would be more code than the switch.
- The fallback case in the switch handles forward-compat — new types render as JSON until someone writes a component.
- TypeScript narrows the type inside each case.

**Tradeoff:** if we got to 30 block types we'd refactor to a `Map<template_id, Component>` registry.

### 6. Why force HTTP/1.1 in the Java HttpClient?

**Decision:** `HttpClient.newBuilder().version(Version.HTTP_1_1)`.

**Why:** we hit a real bug. Java's HttpClient defaults to HTTP/2 and tries to upgrade. Uvicorn (the Python ASGI server) with `httptools` parser stalls on the HTTP/2 preface for streaming POSTs and the body lands as `null` in FastAPI. Forcing `Version.HTTP_1_1` skips negotiation and works perfectly.

**This is exactly the kind of "boring infra detail" interviewers love.** Tells the story of debugging — not just "I built it."

---

## Hard problems (be ready to tell these stories)

Each follows a STAR-ish format: **S**ymptom → **T**race → **A**nalysis → **R**esolution. Pick 2–3 to memorize.

### Story 1: The "Connection Lost" bug

**Symptom:** First query worked. Subsequent queries showed "Connection lost." Frontend stuck in busy state. Enter key wouldn't send.

**Trace:** Backend logs showed a stack trace **after** the SSE stream completed — `org.springframework.security.access.AccessDeniedException: Access Denied`. But the request had been authenticated (the controller ran, blocks were persisted).

**Analysis:** When `SseEmitter.complete()` fires, Tomcat re-dispatches the response back through the filter chain on a **different thread** to commit the response. That thread has no `SecurityContext`. Spring's `AuthorizationFilter` runs again on the async dispatch and throws AccessDenied — too late to send a response (already committed), but it leaves an exception in the logs and corrupts the connection from the browser's POV.

**Resolution:**
```java
.authorizeHttpRequests(a -> a
    .dispatcherTypeMatchers(DispatcherType.ASYNC, DispatcherType.ERROR).permitAll()
    .requestMatchers("/api/auth/**").permitAll()
    .anyRequest().authenticated()
)
```

The original request was already authenticated; ASYNC and ERROR dispatches are internal. Permitting them was the fix.

**Why this answer impresses:** shows you understand *Spring's request lifecycle*, not just `@RestController`.

### Story 2: The empty-body 422

**Symptom:** Backend reported `Research agent returned 422` on every query. FastAPI said body was missing.

**Trace:**
1. Logged the JSON the Java client was about to send → 106 bytes, valid.
2. `wget` from inside the backend container to the agent → worked perfectly.
3. So the bug was Java HttpClient → uvicorn specifically.

**Analysis:** Java's `HttpClient` defaults to HTTP/2 and attempts the HTTP/2 upgrade ("h2c"). Uvicorn with the default `httptools` parser doesn't speak h2c on the streaming path; the upgrade attempt confuses framing and the body never lands.

**Resolution:** one-line change — `.version(HttpClient.Version.HTTP_1_1)` on the client builder.

**Why this answer impresses:** shows you can debug across two languages and two HTTP libraries; shows you understand HTTP version negotiation.

### Story 3: The auto-scroll fight

**Symptom:** During streaming, every checkpoint forced the chat to scroll to the bottom. Users couldn't scroll up to read older parts of the answer — the stream kept yanking them back.

**Analysis:** `useEffect(scrollToBottom, [checkpoints.length, messages.length, streaming])` was running on *every* checkpoint regardless of where the user was. Smooth scroll behavior fought against manual wheel scrolling.

**Resolution:** track a `stickToBottomRef` that's `true` only when the user is within 80px of the bottom. Update it on user `onScroll`. Auto-scroll only when stuck. Use `behavior: "auto"` (instant) during streaming so rapid checkpoints don't visually jitter; `behavior: "smooth"` only on natural transitions.

**Why this answer impresses:** shows you think about UX, not just code; the standard "scroll to bottom on update" pattern is wrong and you knew it.

### Story 4: The map looked dead

**Symptom:** Backend correctly emitted 15 markers for "restaurants near Connaught Place." The map showed only one pin. Tiles looked light when they should've been dark.

**Trace:** Inspected the DOM — all 15 markers present. Filter chain showed CSS `.leaflet-container { filter: hue-rotate(180deg) invert(0.9) }` was being applied to *everything*, including markers (rotating brand violet → murky teal) and popups (white text on black background turning into black text on white).

**Resolution:**
- Move the filter from `.leaflet-container` to `.leaflet-tile-pane` only. Tiles dark, pins/popups untouched.
- Replace default marker icon with a custom `L.divIcon` SVG — gradient violet→pink→cyan to match the brand.
- Static `zoom={13}` made the markers cluster into a tiny visual area on a city-wide view. Add a `FitToMarkers` child component that calls `map.fitBounds(latLngBounds(markers))` so the view auto-fits to the actual extent.

**Why this answer impresses:** shows you can debug CSS filter inheritance and you care about pixel-level polish.

### Story 5: Adaptive UI for unknown blocks

**Story:** "What happens when the agent invents a new block type tomorrow?"

**Answer:**
- Pydantic schemas on the agent side define `template_id: Literal["markdown"|"data-table"|...]`.
- Mirrored TypeScript discriminated union on the frontend.
- The TypeScript union has a *catch-all* branch: `| { template_id: string; data: unknown }`.
- `BlockRenderer` is a switch over known template IDs with a `default → FallbackBlock` case.
- `FallbackBlock` shows a collapsible JSON viewer with the unknown shape.

So if the agent emits a `bar-chart` block before we ship the React component, the user sees a pretty JSON viewer instead of a crashed page. Then we ship the component at our leisure.

**Why this answer impresses:** shows you design for forward compatibility and graceful degradation.

---

## Concepts they will probe

### "Explain the ReAct loop in your own words."

> "The model gets the user query plus a list of tool definitions. It outputs either a final answer or a structured tool call — name plus arguments. Our agent runtime executes the tool, appends the result to the message history, and feeds it back to the model. The model decides whether it has enough or needs another tool call. That's the loop: Reason → Act → Observe → repeat. Deep Agents adds three things on top: a `write_todos` tool so the model plans before executing, a `read_file`/`write_file` scratch space for multi-step research, and automatic context compaction at ~85% of the window."

### "What is prompt caching and how do you use it?"

> "Anthropic's API lets you mark message blocks with `cache_control`. The first call processes them normally, subsequent calls within ~5 minutes pull from server-side cache for ~90% of the input cost on those tokens. We mark the system prompt and tool schemas — they're identical across requests for the same agent, ~2KB stable. So the second call onwards pays input cost mostly on the user's actual query, not on the boilerplate."

### "Why TypeScript on the frontend?"

> "The frontend deals with a typed API surface — auth responses, conversation lists, message shapes, and especially the heterogeneous block types. Without TypeScript, every block render path is a `if (block.template_id === 'leaflet-map') block.data.markers …` and you find out at runtime if the shape is wrong. With TypeScript discriminated unions, the compiler tells me before I ship that I touched a field that doesn't exist on this branch. Auth responses, axios calls, Zustand state are all typed end-to-end. We caught two block-shape bugs at compile time during the bar-chart removal cleanup — saved a runtime error in front of a user."

### "What's a JSONB column? Why not a separate table?"

> "JSONB is Postgres's binary JSON type. It indexes well (GIN), supports containment queries (`@>`), and lets us store variable-shape data without a rigid schema. The blocks list per message is heterogeneous — modeling it as a table would mean either polymorphic associations or one table per block type. JSONB stays simple and queryable. We pay a small storage cost (Postgres re-parses JSON on each query) but it's negligible at our data volume."

### "What happens if the LLM call fails?"

> "Three layers of resilience. First, OpenRouter has automatic provider failover — if Anthropic 5xx's, OpenRouter tries another provider behind the same `anthropic/claude-sonnet-4-6` model ID. Second, our agent code catches exceptions in the streaming loop and emits an SSE `error` event so the frontend shows a clean message, not a hang. Third, if OpenRouter itself is down we fall back to OpenAI GPT-4o using the same LangChain `ChatOpenAI` interface — different `base_url` and `api_key`. The model is built lazily so the first request after a failover is the only one paying the connection cost."

### "Walk me through what happens when I ask 'Bitcoin price in INR'."

This is your time to shine. The full sequence is in `PROJECT_OVERVIEW.md` ("How the streaming actually flows"). Memorize at least the steps:
1. Frontend POST → Spring Boot
2. Spring persists user message
3. Spring opens HTTP/1.1 stream to FastAPI agent
4. Agent runs Deep Agents loop, calls `get_crypto_price` tool
5. Tool checks Redis cache → miss → CoinGecko HTTP call → cache result
6. Each `on_tool_start`/`on_tool_end` becomes an SSE checkpoint
7. LLM produces final markdown answer
8. `block_formatter` builds `[MarkdownBlock, InsightCardsBlock]`
9. SSE `blocks` event back through Spring
10. Spring persists assistant message + blocks JSONB
11. Frontend `BlockRenderer` paints the markdown + insight card

### "What would you scale first?"

> "Before scaling, I'd add metrics — Prometheus is already wired in the agent. The first thing to break under load is the agent: each request holds an LLM connection for several seconds. So:
> 1. Horizontal scale the agent service. Stateless, easy.
> 2. Move LLM calls behind a queue — Celery or Redis-backed work queue — so heavy bursts smooth out.
> 3. Add Redis read-replicas — tool cache hit rate is the biggest free lunch.
> 4. Backend is JVM, can serve a lot per node; rate-limit per user with Bucket4j before scaling out.
> 5. Postgres scaling: read replicas for `messages` queries (transcripts), connection pooling via PgBouncer."

### "Why didn't you use [LangChain Agents / OpenAI Assistants / vector DB]?"

| If they ask… | Answer |
|---|---|
| Vector DB / RAG | "Our queries are typically real-time data lookups — prices, news, places. RAG would help if we had a corpus to index. Wikipedia, Exa, and Tavily already cover unstructured knowledge with fresher data than any index we'd build." |
| OpenAI Assistants API | "Assistants is OpenAI-specific. We use OpenRouter so we can swap to Claude, Gemini, etc. at one config flip. Deep Agents on top of LangGraph gives us model-agnostic orchestration." |
| LangChain Agents (`AgentExecutor`) | "Deep Agents is purpose-built for our shape — middleware-based ReAct with built-in planning (`write_todos`), file scratch, automatic context compaction, and tool-call repair. LangChain's older `AgentExecutor` doesn't compose middleware as cleanly." |
| Plain function calling without a framework | "We did consider it. The win from Deep Agents is auto-compaction at 85% of the window — for long research sessions the model would otherwise hit context limits. We'd rebuild that ourselves; better to use the library." |

---

## Likely "what would you do differently?" answers

Pick whichever is honest:

- **More tests.** End-to-end tests with Testcontainers for Postgres + WireMock for OpenRouter would catch regressions on the SSE pipeline. Right now there's a smoke test only.
- **Streaming the markdown token-by-token.** Currently we emit the final markdown in one `blocks` event. We could stream tokens to the frontend like ChatGPT does. Tradeoff: more SSE complexity for marginal UX win when most answers come back in 5 seconds.
- **Audit log table.** Every tool call should land in an audit table for postmortem. Right now they're only in Redis cache + agent logs.
- **Per-conversation memory.** Today the agent gets the message history but no longer-term memory ("user mentioned they live in Bangalore three days ago"). A `user_facts` table populated by an extraction pass would unlock that.
- **OAuth.** Email/password works; OAuth via Google would lower signup friction.

---

## Lines that sound senior

> "We optimized the second-most-common path before the most-common one — dedup before LLM call." (= cache before compute)
>
> "The block type is a discriminated union, so removing bar-chart was a TypeScript-guided refactor — we just deleted the union branch and the compiler told us every place to touch."
>
> "I picked SSE because the failure mode is observable — `curl -N` shows you exactly what the server is sending. WebSocket failures need wireshark."
>
> "JSONB was a deliberate denormalization — blocks are leaf data, no foreign keys point in or out, and the query patterns we have don't benefit from a relational shape."
>
> "We force HTTP/1.1 because the alternative was a one-line config change versus understanding why uvicorn-httptools breaks h2c framing on streaming POSTs."
>
> "The async dispatch authorization issue is a Spring Security gotcha — easy to miss until you have an SSE endpoint behind auth."

---

## Three live-coding questions you might get

### "Add a `pie-chart` block to this system."

What you'd say out loud:

1. Add `PieChartBlock(template_id: Literal["pie-chart"], data: PieChartData)` in `research-agent/src/research_agent/blocks/schemas.py`.
2. Add it to the `Block` discriminated union.
3. In `block_formatter.py`, emit it from a tool result that returns slice data — e.g. portfolio breakdown.
4. Mirror in `frontend/src/types.ts` — add the branch to the `Block` union.
5. Create `frontend/src/components/blocks/PieChartBlock.tsx` using `recharts` (we'd re-add it).
6. Add the `case "pie-chart"` in `BlockRenderer.tsx`.
7. Done. No backend Java changes — Java treats `blocks` as opaque JSONB.

### "How would you add 'remember my preferences' to the agent?"

1. New table `user_facts(user_id, fact_text, source_message_id, created_at)`.
2. New backend endpoint `GET /api/conversations/{id}/query` *also* extracts facts after the assistant completes — small LLM call: "From this user message, extract any durable facts about the user (location, preferences). Return JSON."
3. Inject facts into the agent's system prompt: `"User context: <fact1>; <fact2>; …"`.
4. Cache the system prompt with prompt-caching so the per-user variant doesn't blow input cost.

### "There's a bug — the user reports the chat scrolls weirdly. Walk me through how you'd debug it."

1. Reproduce. Open the app, send a long query.
2. Inspect — is the issue auto-scroll-during-stream, scroll-jumping-on-new-message, or scroll-not-going-down-when-expected?
3. Open `ChatPanel.tsx`, find the `useEffect` with scroll behavior. Check its dependency array.
4. Check the `onScroll` handler — is it correctly tracking `stickToBottomRef`?
5. Check CSS `overscroll-behavior` — is the inner scroll bouncing the outer one?
6. Use React DevTools to watch state during a stream — is the component re-rendering 100x per second?
7. Fix narrow root cause. Don't use `behavior: "smooth"` during high-frequency updates — switches to `auto`.

---

## A confident close

When the interviewer says "any questions for us?":

- "What does your testing strategy look like for streaming endpoints? I struggled to write good tests for SSE — would love to learn how you approach it."
- "How do you think about LLM costs at scale? We're using OpenRouter prompt caching, but I'm curious what works at higher volume."
- "What's the biggest production AI system you've shipped, and what surprised you?"

Show curiosity, especially in their AI strategy. That's the territory you're moving into.
