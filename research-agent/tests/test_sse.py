import asyncio
import json
import time

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError

from research_agent import http_handler
from research_agent.agent import tools
from research_agent.blocks import follow_up_generator
from research_agent.http_handler import ResearchRequest, stream_research

METRIC_KEYS = {
    "request_id", "outcome", "total_latency_ms", "first_checkpoint_ms", "model", "llm_calls",
    "input_tokens", "output_tokens", "total_tokens", "follow_up_model", "follow_up_input_tokens",
    "follow_up_output_tokens", "tool_call_count", "tools", "search_providers", "query_chars",
    "history_messages", "error",
}


def parse_sse(chunks: list[str]) -> list[tuple[str, dict]]:
    events = []
    for chunk in chunks:
        for block in chunk.split("\n\n"):
            if not block.strip():
                continue
            name, data = None, None
            for line in block.splitlines():
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
            events.append((name, data))
    return events


async def collect(req: ResearchRequest) -> list[tuple[str, dict]]:
    return parse_sse([chunk async for chunk in stream_research(req)])


class FakeAgent:
    def __init__(self, events=(), exc=None, delay=0.0):
        self.events = list(events)
        self.exc = exc
        self.delay = delay

    async def astream_events(self, *args, **kwargs):
        for ev in self.events:
            yield ev
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc:
            raise self.exc


def use_agent(monkeypatch, agent=None, exc=None):
    async def get_agent():
        if exc:
            raise exc
        return agent

    monkeypatch.setattr(http_handler, "get_agent", get_agent)


@pytest.fixture(autouse=True)
def reset_follow_up_client():
    follow_up_generator.reset_client()
    yield
    follow_up_generator.reset_client()


def final_answer(text, usage=None):
    msg = AIMessage(content=text, usage_metadata=usage or {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5})
    return {"event": "on_chat_model_end", "data": {"output": msg}}


def assert_contract(events):
    names = [e[0] for e in events]
    assert names[0] == "checkpoint"
    assert names[-1] == "done"
    assert names.count("done") == 1
    assert set(events[-1][1]["metrics"]) == METRIC_KEYS


async def test_success_ends_with_done_and_metrics(monkeypatch):
    agent = FakeAgent([
        {"event": "on_tool_start", "name": "web_search", "data": {"input": {"query": "x"}}},
        {"event": "on_tool_end", "name": "web_search", "data": {"input": {"query": "x"}, "output": "1. **a**\n   b\n   Source: https://a.com"}},
        final_answer("The answer."),
    ])
    use_agent(monkeypatch, agent)
    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    names = [e[0] for e in events]
    assert names.index("blocks") == len(names) - 2
    done = events[-1][1]
    assert done["status"] == "completed"
    m = done["metrics"]
    assert m["outcome"] == "completed"
    assert m["tool_call_count"] == 1
    assert m["input_tokens"] == 3 and m["output_tokens"] == 2 and m["total_tokens"] == 5
    assert m["first_checkpoint_ms"] is not None
    assert events[-2][1]["data"]["sources"] == ["https://a.com"]


async def test_stream_exception_sends_generic_error_then_done(monkeypatch):
    use_agent(monkeypatch, FakeAgent(exc=RuntimeError("upstream said sk-or-v1-SECRET at http://10.0.0.1")))
    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    assert [e[0] for e in events][-2:] == ["error", "done"]
    assert events[-2][1]["content"] == http_handler.GENERIC_ERROR
    assert "SECRET" not in json.dumps(events)
    assert events[-1][1]["status"] == "failed"
    assert events[-1][1]["metrics"]["error"] == "RuntimeError"


async def test_agent_init_failure_sends_error_then_done(monkeypatch):
    use_agent(monkeypatch, exc=RuntimeError("No LLM API key configured sk-123"))
    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    assert [e[0] for e in events] == ["checkpoint", "error", "done"]
    assert "sk-123" not in json.dumps(events)


async def test_recursion_limit_sends_error_then_done(monkeypatch):
    use_agent(monkeypatch, FakeAgent(exc=GraphRecursionError("limit")))
    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    assert events[-2] == ("error", {"status": "failed", "content": http_handler.STEP_LIMIT_ERROR})


async def test_block_formatting_failure_sends_error_then_done(monkeypatch):
    use_agent(monkeypatch, FakeAgent([final_answer("ok")]))

    def boom(*a, **k):
        raise ValueError("internal detail")

    monkeypatch.setattr(http_handler, "format_blocks", boom)
    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    assert events[-2][0] == "error"
    assert "internal detail" not in json.dumps(events)


async def test_clarification_then_done(monkeypatch):
    use_agent(monkeypatch, FakeAgent([final_answer("[CLARIFICATION] Which city?")]))
    events = await collect(ResearchRequest(query="nearest atm"))
    assert_contract(events)
    assert [e[0] for e in events] == ["checkpoint", "clarification", "done"]
    assert events[1][1]["content"] == "Which city?"
    assert events[-1][1]["status"] == "completed"


async def test_overall_timeout_sends_error_then_done(monkeypatch, settings):
    monkeypatch.setattr(settings, "REQUEST_TIMEOUT_SECONDS", 0.3)
    use_agent(monkeypatch, FakeAgent(delay=10))
    started = time.perf_counter()
    events = await collect(ResearchRequest(query="q"))
    assert time.perf_counter() - started < 2
    assert_contract(events)
    assert events[-2] == ("error", {"status": "failed", "content": http_handler.TIMEOUT_ERROR})
    assert events[-1][1]["metrics"]["outcome"] == "timeout"


async def test_client_disconnect_cancels_agent(monkeypatch):
    cancelled = asyncio.Event()

    class SlowAgent:
        async def astream_events(self, *a, **k):
            try:
                yield {"event": "on_tool_start", "name": "web_search", "data": {"input": {"query": "x"}}}
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    use_agent(monkeypatch, SlowAgent())
    gen = stream_research(ResearchRequest(query="q"))
    await gen.__anext__()
    await gen.__anext__()
    await gen.aclose()
    await asyncio.wait_for(cancelled.wait(), 1)


async def test_follow_up_failure_does_not_break_stream(monkeypatch):
    use_agent(monkeypatch, FakeAgent([final_answer("Answer")]))

    async def boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(http_handler, "generate_follow_ups", boom)
    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    assert events[-2][0] == "blocks"
    assert events[-2][1]["data"]["follow_ups"] == []


async def test_real_deep_agent_metrics_end_to_end(monkeypatch, memory_cache):
    from deepagents import create_deep_agent

    class FakeModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    model = FakeModel(responses=[
        AIMessage(
            content="",
            tool_calls=[
                {"name": "web_search", "args": {"query": "a"}, "id": "c1"},
                {"name": "web_search", "args": {"query": "b"}, "id": "c2"},
            ],
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        ),
        AIMessage(
            content="Final answer with facts.",
            usage_metadata={"input_tokens": 300, "output_tokens": 50, "total_tokens": 350},
        ),
    ])
    agent = create_deep_agent(model=model, tools=[tools.web_search], system_prompt="test")
    monkeypatch.setattr(tools.settings, "OCTEN_API_KEY", "")
    monkeypatch.setattr(tools.settings, "TAVILY_API_KEY", "")
    monkeypatch.setattr(tools, "_ddg_search_sync", lambda q: [{"title": q, "body": "b", "href": f"https://{q}.com"}])
    use_agent(monkeypatch, agent)

    events = await collect(ResearchRequest(query="q"))
    assert_contract(events)
    m = events[-1][1]["metrics"]
    assert m["outcome"] == "completed"
    assert m["tool_call_count"] == 2
    assert m["llm_calls"] == 2
    assert (m["input_tokens"], m["output_tokens"], m["total_tokens"]) == (400, 70, 470)
    assert [t["name"] for t in m["tools"]] == ["web_search", "web_search"]
    assert all(t["success"] and not t["cache_hit"] for t in m["tools"])
    assert m["search_providers"] == ["duckduckgo", "duckduckgo"]
    blocks = events[-2][1]["data"]
    assert set(blocks["sources"]) == {"https://a.com", "https://b.com"}


def test_build_messages_uses_ist_date(monkeypatch):
    msgs = http_handler._build_messages(ResearchRequest(
        query="hello",
        conversation_history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}],
    ))
    assert len(msgs) == 3
    assert http_handler.today_ist() in msgs[-1].content
    assert http_handler.IST.utcoffset(None).total_seconds() == 19800
