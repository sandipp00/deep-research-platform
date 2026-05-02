# AI Learning Roadmap (Mid-2026 edition)

For someone shifting from full-stack / backend to AI engineering. Written assuming you can already code, ship, and reason about systems — so this skips Python 101 and goes straight to what actually matters in 2026.

The field has split into three career tracks. Pick early, then go deep.

| Track | What you build | Where the jobs are |
|---|---|---|
| **AI engineer / applied AI** | Apps that *use* LLMs (like Lumen). Agents, RAG, structured outputs, tool use. | Most companies. Highest growth. **Best fit for you given Lumen.** |
| **ML engineer** | Production ML pipelines: training, serving, monitoring, MLOps. Often classical models. | Large product companies, fintech, ad tech. |
| **Research / model engineer** | Train / fine-tune models. Reads papers, runs experiments. | Frontier labs (Anthropic, OpenAI, DeepMind), top startups. PhD-flavored. |

This roadmap targets **AI engineer**. Adjust if you want the other tracks.

---

## Phase 0 — The brutal foundations (1–2 weeks part-time)

You don't need to grind Andrew Ng if you already code. You do need *just enough* math to read papers without panic.

### Math (just enough)

- **Linear algebra**: vectors, dot products, matrix multiply, eigenvectors. *3Blue1Brown's "Essence of Linear Algebra"* — 14 short YouTube videos. That's it.
- **Probability**: Bayes' theorem, conditional probability, expectation. Khan Academy's Statistics & Probability if you're rusty.
- **Calculus**: chain rule, gradients. Don't go deeper than that.

### Python for AI

- `numpy` — array ops, broadcasting
- `pandas` — read CSVs, filter, group
- Type hints, async/await, context managers (you're already there from Lumen)

**Time cap: 2 weeks max.** Don't get stuck here. Most AI engineering work is *integration*, not derivatives.

---

## Phase 1 — How LLMs actually work (1 week)

You need a working mental model. Not "I can train one from scratch" — "I can predict why this prompt does this."

### Watch / read in this order

1. **3Blue1Brown's "But what is a GPT?"** (YouTube, 27 min). Visual intuition for transformers.
2. **Karpathy's "Let's build GPT from scratch"** (YouTube, 2 hours). Code along. You'll get tokenization, attention, training loops.
3. **Karpathy's "Intro to LLMs"** (YouTube, 1 hour). The mental model — pre-training, post-training, RLHF, hallucinations, jailbreaks.
4. **The Illustrated Transformer** by Jay Alammar (blog post). Gold-standard explainer.

After this you'll know what tokens are, what attention does, what the context window means, why models hallucinate, and why prompt engineering works.

### Hands-on

Run **`llama.cpp`** or **`Ollama`** locally with a small model (Llama 3.1 8B or Phi-4). Feel the difference between a 1B and a 70B model. Understand quantization (FP16 → INT8 → INT4) — it explains why "smaller, faster, dumber" is a knob.

---

## Phase 2 — AI engineering with APIs (2–3 weeks) — *this is where you live*

This is your bread and butter. The tools you used in Lumen, but understood in depth.

### Anthropic API (Claude)

- **The official Anthropic SDK** for Python and TypeScript.
- **Prompt caching** — the trick that took 90% off your input cost in Lumen. Read Anthropic's docs end-to-end.
- **Tool use** (function calling) — `tools=[…]`, `tool_choice`, parallel tool calls.
- **Extended thinking** — Claude's reasoning mode. Read when to use it (math, multi-step planning) and when not (it's slower).
- **Vision** — pass images, get back analysis.
- **Citations** — first-class API for grounded responses.
- **Files API** — long documents.
- **Memory** — conversation memory primitives.
- **Batch API** — async bulk processing at half cost.

Build: a CLI tool that takes a screenshot of your terminal, asks Claude to explain the error, suggests a fix.

### OpenAI / Gemini / etc.

Skim the others — Anthropic, OpenAI, Google all converge on the same shapes (chat completions, tools, structured outputs, vision). When you know one, you know all.

### Structured outputs

How to make an LLM return parseable JSON every time:

- **JSON mode** / `response_format`
- **Tool use as a JSON forcer** — define a tool with the schema you want; force the model to call it.
- **Pydantic + Instructor** library — Python pattern for typed LLM responses.

Build: a feedback parser. Given a paragraph of free-text user feedback, return `{sentiment, themes[], priority, suggested_owner}` as a typed object every time.

### Streaming

You did this in Lumen. Now learn it more deeply.
- Server-Sent Events (SSE) is the dominant pattern. WebSockets when you need bidirectional.
- Token-by-token streaming for that "ChatGPT typing" feel.
- Tool-call streaming — partial JSON arrives mid-stream; how to render progress without breaking parsing.

---

## Phase 3 — Agents (2–3 weeks) — *the 2026 frontier*

You already shipped one. Now go deeper.

### The frameworks worth knowing

| Framework | Use it when |
|---|---|
| **Anthropic's Claude Agent SDK** | Production agentic apps with Anthropic, MCP-native, sandboxing. **Most relevant to where the field is going.** |
| **LangGraph + Deep Agents** | What you used in Lumen. Graph-based orchestration, middleware-rich, model-agnostic. |
| **OpenAI Agents SDK / Assistants API** | OpenAI ecosystem. Hosted state, code interpreter built-in. |
| **Pydantic AI / Instructor** | Type-safe agent code in Python. Newer but ergonomic. |
| **smolagents** (HuggingFace) | Small agents that run in code-execution loop. Worth a peek. |

### Concepts to master

- **ReAct loop** — Reason → Act → Observe. The grandfather pattern.
- **Plan-and-Execute** — model writes a plan, then executes step by step. Better for long horizons.
- **Multi-agent / orchestrator-worker** — a router agent dispatches to specialist agents. The Alvoff Planning Agent → Research Agent shape.
- **Tool design**: idempotent, narrowly scoped, well-named, well-described. Tool descriptions are 30% of agent quality.
- **Context management**: agents grow context fast. Compaction, summarization, scratch files.
- **Observability**: every tool call logged, traced, replayable. **LangSmith** is the gold standard for tracing LangChain/LangGraph.

### Build to internalize

1. **A coding agent.** Give it a directory + a goal. It reads files, writes patches, runs tests, iterates. Mini Claude Code.
2. **A research agent.** ✓ already done — that's Lumen.
3. **A multi-agent system.** Three agents: a planner, a worker, a critic. Planner decomposes a task. Worker does it. Critic reviews and sends back if not good enough.

### Read

- *"Building effective agents"* by Anthropic (2024) — the canonical patterns essay.
- The **Claude Code** open-source repo if you want to see a real agent in production.
- *"The Bitter Lesson"* by Rich Sutton — short essay, foundational worldview.

---

## Phase 4 — RAG and evaluation (2 weeks)

### RAG (Retrieval-Augmented Generation)

When the agent needs to know things outside its training cutoff and outside what tools can fetch — your own internal docs, a knowledge base, a codebase.

- **Embeddings** — what they are, how they're produced. Cosine similarity.
- **Vector databases** — `pgvector`, `Qdrant`, `Pinecone`, `Weaviate`. Start with `pgvector` since you already know Postgres.
- **Chunking strategies** — fixed size, recursive, semantic, parent-document.
- **Hybrid search** — vector + BM25 keyword combined; almost always better than pure vector.
- **Reranking** — Cohere's rerank model, Jina rerank. Re-orders top-k. Cheap, big quality bump.
- **Query rewriting / HyDE** — turn a vague question into a better search query before embedding.

Build: a "search my notes" CLI. Index a folder of markdown. Ask questions. Cite source files.

### Evaluation — *the unsexy thing that separates pros*

If you can't measure your AI system, you can't improve it. Evals matter more than the next prompt tweak.

- **Eval datasets** — curate questions + expected answers (or rubric).
- **Pairwise comparisons** — show two answers, pick the better. Crowdsourced or LLM-judge.
- **LLM-as-judge** — use a stronger model to grade outputs.
- **Tools**: `LangSmith`, `Braintrust`, `Phoenix`, `Promptfoo`, `Inspect AI`.
- **Domain-specific evals** — for code, run the test suite. For SQL, run the query.

Build: take your Lumen agent. Build an eval set of 30 queries. Run them on every code change. Track regressions.

---

## Phase 5 — MCP, the new plumbing (1 week)

**Model Context Protocol** is the standard way agents talk to external tools/data. Anthropic-led, now an open standard.

- **What it is**: a JSON-RPC protocol that lets LLMs invoke tools / read resources / sample LLMs across processes.
- **Why it matters**: instead of every app re-implementing tool wiring, MCP servers are reusable. There's a registry of community servers (Postgres, Slack, GitHub, filesystem, browser, etc.).
- Build: a custom MCP server (e.g., your company's internal API). Hook it up to Claude Code or Claude Desktop. Now any MCP-capable agent can use it.

This is where the industry is going. Be early.

---

## Phase 6 — Production AI (3 weeks)

What you didn't get to learn in school:

### Cost control

- Cache aggressively. Prompt caching, response caching, embedding caching.
- Tier your models — cheap model for triage / routing, expensive model only when needed.
- Batch when latency allows. Anthropic's Batch API is half cost.
- Watch input tokens; output tokens are 4x more expensive but bounded.

### Latency

- First-token latency (TTFT) vs total response time — tune for the right one.
- Streaming as a UX hack — perceived latency drops 80% even if total is the same.
- Speculative decoding, draft models — frontier territory but read about it.

### Safety / abuse

- Prompt injection — the #1 prod issue. Treat tool outputs as untrusted.
- Jailbreaks — what they look like, how providers defend.
- PII redaction — never paste raw user data into a model without thinking about it.
- Output filtering — moderation API, banned-word lists, structured-output guards.

### Observability

- Trace every LLM call: prompt, response, latency, cost, model version.
- Sample-and-replay — keep a percentage of prod traffic to re-run after prompt changes.
- A/B testing prompts in production. Tools: `LaunchDarkly` for the gate, `LangSmith` for the data.

### Security

- API key rotation. Per-user keys vs per-app.
- Sandboxing tool execution — agents that write code or hit shells need real isolation.
- Rate limits per user.

---

## What to *build* (in priority order)

You learn AI engineering by shipping. In rough difficulty:

1. **A CLI Q&A bot** — wrap Claude API + a system prompt. 1 day.
2. **A typed extractor** — paragraph in, JSON out. 1 day.
3. **A RAG system over your own docs** — pgvector + Claude. 3 days.
4. **A coding agent** — reads/writes files, runs tests. 1 week.
5. **A multi-step research agent** — like Lumen, but with a different domain. 1 week.
6. **An eval harness** for one of the above. 3 days.
7. **A custom MCP server** for some API you care about. 2 days.

By #6 you can put "AI engineer" on your CV and mean it. By #7 you're ahead of most people calling themselves that.

---

## Stay current (without drowning)

The field moves weekly. Pick **one** signal-rich source per category:

| Category | One source |
|---|---|
| Anthropic news | The Anthropic blog + their YouTube ("How to build with Claude") |
| Field-wide news | **The Batch** (DeepLearning.AI weekly newsletter) |
| Papers worth reading | **Sebastian Raschka's blog** + **Lilian Weng's blog** (when she posts) |
| Twitter/X follow list | Karpathy, Simon Willison (`@simonw`), Jim Fan, Riley Goodside, Anthropic team |
| Hacker News AI | Just read the front page once a day |
| Papers to skim | `arxiv-sanity`, but only when something specific catches you |

**Skip**: most YouTube AI hype channels. Most LinkedIn AI thought leaders. Most "X new agent framework dropped" tweets — wait two weeks; if it survives, then look.

---

## Books worth your time

- **"Designing Machine Learning Systems"** — Chip Huyen. The standard text on production ML. Read cover-to-cover.
- **"Building LLM-Powered Applications"** — Valentina Alto. Practical, code-heavy.
- **"Hands-On Large Language Models"** — Jay Alammar & Maarten Grootendorst. Best illustrated.

You don't need many books. Twelve good blog posts beat any one book.

---

## What signals to give in interviews

You're shifting from full-stack to AI. That's a story to tell *positively*:

- **Lumen is the bridge.** It's a serious AI app you built end-to-end with real LLM, real tools, real streaming, real production concerns. That's better than a tutorial portfolio.
- **You bring infra hygiene.** You force HTTP/1.1 because you understood the bug. You think about security context propagation. You design for forward compat. AI-only people often miss this stuff.
- **You're product-minded.** You care that the map looks good, that scroll doesn't fight the user. That's underrated.

What to *not* do:
- Don't pretend you've trained models from scratch. Most AI engineers haven't either.
- Don't memorize paper abstracts. Demonstrate a working mental model.
- Don't oversell the ML math. Be honest — "I learned just enough linear algebra to read papers, I haven't derived backprop in a year."

---

## A 90-day plan if you only have weekends

| Weekend | Focus | Deliverable |
|---|---|---|
| 1 | Phase 0 + 1 catch-up | Watched Karpathy, ran Ollama locally |
| 2 | Anthropic API deep dive | CLI Q&A bot with prompt caching |
| 3 | Tool use | Extractor that returns typed JSON |
| 4 | Streaming | "Typing" UI in front of any model |
| 5 | RAG basics | pgvector + your-docs Q&A |
| 6 | Evals | Eval harness over the RAG bot |
| 7 | Agent fundamentals | One-tool ReAct agent from scratch (no framework) |
| 8 | LangGraph / Deep Agents | Multi-tool agent with planning |
| 9 | MCP | Custom MCP server, used by Claude Desktop |
| 10 | Multi-agent | Planner + worker + critic |
| 11 | Polish | Pick best project, deploy, write a blog post |
| 12 | Job apply | Resume, polished GitHub, story memorized |

**12 weekends. ~96 hours of focused work.** That's enough to get hired as a junior AI engineer with the foundation Lumen gave you.

---

## Final advice

The best AI engineers right now are people who **ship**. Not people who can name every paper. The field is too new for credentialism — what gets you hired is "show me what you built, walk me through how it works, tell me where you got stuck."

You already have Lumen. Add one more focused project (a coding agent or a domain-specific RAG). Have a blog post about a non-obvious bug you fixed. Be ready to talk for 20 minutes about how a transformer turns tokens into the next token.

That's it. You're closer than you think.
