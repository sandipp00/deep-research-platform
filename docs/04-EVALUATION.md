# Evaluation

Companion to [`01-PROJECT-DEEP-DIVE.md`](./01-PROJECT-DEEP-DIVE.md). There is **no evaluation harness in this repo today** — no `evals/` directory, no token/latency/cost instrumentation, no golden dataset. This doc is two things: (1) what to instrument in the code before evaluation is even possible, and (2) the evaluation suite to build on top of that instrumentation.

## Why this needs code changes first, not just a test suite

You can't evaluate cost or latency you never measured, and you can't grade "did it use the right tool" without a log that says which tool it used. Three gaps block evaluation today:

### 1. No usage/cost tracking

`agent/graph.py::_build_model()` builds a `ChatOpenAI` client but nothing in `http_handler.py` reads `response_metadata["token_usage"]` off the final `AIMessage` (OpenRouter, like OpenAI, returns `prompt_tokens`/`completion_tokens` on every response — LangChain surfaces it on `on_chat_model_end` events, which `stream_research` already iterates over but currently discards). **Add:** capture `usage` on the `on_chat_model_end` branch in `http_handler.py`, multiply by the [pricing table already in the README](../README.md#performance--cost) ($0.15/$0.60 per M tokens for DeepSeek V4.1 Flash), and include `{prompt_tokens, completion_tokens, cost_usd}` in the final `blocks` SSE payload. Free per-request cost visibility, and the thing every eval run below needs to report a `$/query` number instead of guessing from token counts after the fact.

### 2. No per-tool or per-request latency tracking

`checkpoint_formatter.py` emits human-readable progress strings but no timestamps. **Add:** wrap the `on_tool_start`/`on_tool_end` handling in `http_handler.py` with `time.monotonic()` deltas, and emit a `duration_ms` alongside each `checkpoint`. Also time the whole request (first byte to `done` event) — that's the number that matters for the README's "sub-second search" / "$X per query" claims to be backed by real data instead of vendor docs.

### 3. No request tracing

Nothing ties a `web_search` call to the specific query that triggered it end-to-end in logs. **Add:** a `request_id` (`uuid4()` per `/research` call, or reuse Postgres's `Message.id` from the backend) threaded through `logger` calls and included in every SSE `checkpoint`/`error` event — makes "why did this eval case fail" a log grep instead of a guess.

None of these are large changes (a few `logger.info`/dict-field additions in `http_handler.py`), but they're the prerequisite — everything below assumes they exist.

## What to evaluate

Four categories, mapped to what's actually built:

| Category | What it checks | Why it matters here |
|---|---|---|
| **Tool selection** | Did the agent call the *right* tool for the query? (e.g. a stock-price question must call `get_stock_price`, not `web_search` — the system prompt in `agent/graph.py` is explicit about this) | The system prompt has hard rules ("NEVER use web_search for a price lookup") specifically because the wrong tool call degrades the UI (prose instead of an `insight-cards` block). This is the single most regression-prone piece of prompt engineering in the repo. |
| **Answer quality** | Is the final answer correct, grounded in tool output (not hallucinated), and does it follow the response guidelines (≤400 words, cites sources, correct language)? | The model is now DeepSeek V4.1 Flash, not Claude — this is exactly the kind of swap that silently degrades instruction-following unless it's measured. |
| **Block correctness** | Did `block_formatter.py` produce the right block types from tool output? (`nearby_places` → map + table, financial tools → insight-cards) | This is deterministic parsing code, not the LLM — it should have near-100% pass rate, and a regression here is a real bug, not "the model got creative." |
| **Cost & latency** | Tokens, $ per query, wall-clock time to first checkpoint / to final answer | The whole pitch of the DeepSeek+Octen swap (see README) is 20-25x cheaper, sub-second search. That claim should be backed by this repo's own eval runs, not just vendor pricing pages. |

## Golden dataset

One JSON file per test case under `research-agent/evals/cases/`, organized by the same categories the system prompt already recognizes:

```json
{
  "id": "stock-001",
  "category": "financial",
  "query": "What's the current price of TCS stock?",
  "expected_tools": ["get_stock_price"],
  "forbidden_tools": ["web_search"],
  "expected_block_types": ["markdown", "insight-cards"],
  "judge_rubric": "Answer states a specific INR price for TCS and does not hedge or refuse."
}
```

Cover every tool at least twice (once straightforward, once ambiguous — e.g. `"nifty"` vs `"Nifty 50"` for `get_stock_price`'s symbol normalization), the clarification path (a deliberately underspecified query like `"find me a hospital"` with no location, which the system prompt says should return `[CLARIFICATION]`, not guess), at least one multi-tool query (e.g. "compare TCS stock price and the latest news about it"), and one query per non-English language the system prompt claims to support (Hindi, Tamil, Kannada, Telugu) to check the "respond in the same language" rule actually holds on the new model.

Avoid asserting exact prices/rates as ground truth (they change every run) — assert *shape* instead: "a `STOCK|` line is present", "the price is a positive number", "the answer mentions a currency symbol". Reserve exact-match assertions for genuinely static facts (Wikipedia-style: "what is the capital of India").

## Suggested harness

A small `research-agent/evals/run_eval.py`, no framework dependency required for v1:

1. Load every case from `evals/cases/*.json`.
2. `POST /research` for each (the same endpoint the frontend hits — this is a black-box eval against the real SSE contract, not an internal unit test), consume the stream, and — once item 1/2/3 above are instrumented — pull `duration_ms`, `cost_usd`, and the list of tools actually called straight off the SSE events.
3. Score deterministically:
   - `tool_selection_pass = actual_tools ⊇ expected_tools and actual_tools ∩ forbidden_tools == ∅`
   - `block_pass = set(block_types) == set(expected_block_types)`
4. Score `judge_rubric` with an **LLM-as-judge** call (a cheap, different model than the one under test — e.g. `gpt-4o-mini` or `deepseek/deepseek-v3` via OpenRouter — avoids the model grading its own homework) — pass/fail plus a one-line reason.
5. Emit a summary table (pass rate per category, p50/p95 latency, total $ for the run) and a JSON artifact for trend tracking across runs.

This is deliberately a thin custom script rather than adopting a framework wholesale, because the thing being tested — SSE checkpoints, block-shaped structured output, tool-call correctness against a specific system prompt — doesn't map cleanly onto any off-the-shelf eval framework's assumptions. Where a framework earns its keep instead of the raw script:

| Tool | Use it for |
|---|---|
| **[Ragas](https://github.com/explodinggym/ragas)** | Faithfulness/groundedness scoring specifically for `web_search`/`wiki_search`-backed answers — checks the answer doesn't say more than the retrieved snippets support. |
| **[DeepEval](https://github.com/confident-ai/deepeval)** or **[promptfoo](https://www.promptfoo.dev/)** | Turns the golden dataset above into `pytest`-style assertions with built-in LLM-as-judge metrics, if the team wants CI integration without hand-rolling the judge call. |
| **[LangSmith](https://www.langchain.com/langsmith)** | Since the agent is already LangGraph/LangChain-based, tracing is close to free (`LANGCHAIN_TRACING_V2=true` + an API key) — gives per-node latency/token breakdown inside the ReAct loop without writing the instrumentation in gap #2 by hand. Worth adopting before hand-rolling `time.monotonic()` calls if budget allows a paid tracing tool. |

## Running it

- **Locally / on demand**: `python evals/run_eval.py --cases evals/cases/ --report evals/results/$(date +%s).json` against a running `research-agent` (real API calls to OpenRouter + Octen — costs real money, keep the golden set small, ~20-40 cases).
- **In CI**: given [`02-DOCKER-CICD.md`](./02-DOCKER-CICD.md) notes there's no test suite wired up yet, don't gate every PR merge on a live-API eval run (flaky, costs money, slow). Instead: a scheduled nightly GitHub Actions workflow (`schedule: cron`) runs the full golden set against `main` and posts the summary (pass rate, cost, p95 latency) to wherever the team already looks — a Slack webhook or a checked-in `evals/results/latest.json` the README badges off of. Run it manually, on-demand, whenever `agent/graph.py`'s system prompt or model changes, or `agent/tools.py`'s provider chain changes (exactly the kind of change this session just made).
- **Regression gate for model/provider swaps specifically**: the next time a model or search provider changes (e.g. DeepSeek → something else, Octen → something else), run the golden set against both old and new config side by side before merging — this is the concrete workflow that would have given the Exa→Octen and Sonnet→DeepSeek swaps in this session a real before/after number instead of "it typechecks."

## What "done" looks like

- [ ] Token usage + cost surfaced in `http_handler.py` and the `blocks` SSE payload
- [ ] Per-tool and per-request latency surfaced the same way
- [ ] `request_id` threaded through logs and SSE events
- [ ] `research-agent/evals/cases/*.json` — 20-40 cases covering all 8 tools, clarification path, multi-tool queries, non-English queries
- [ ] `research-agent/evals/run_eval.py` — runs the set, scores deterministically + LLM-as-judge, emits a summary
- [ ] One documented baseline run (current DeepSeek V4.1 Flash + Octen config) checked into `evals/results/baseline.json` so every future change has something to diff against
