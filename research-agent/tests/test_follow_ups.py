from types import SimpleNamespace

import pytest

from research_agent.blocks import follow_up_generator as fug
from research_agent.metrics import RequestMetrics, bind_metrics


@pytest.fixture(autouse=True)
def reset():
    fug.reset_client()
    yield
    fug.reset_client()


def test_no_keys_means_no_client():
    assert fug._get_client() == (None, "")


def test_shared_client_uses_agent_provider(monkeypatch, settings):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    c1, model = fug._get_client()
    c2, _ = fug._get_client()
    assert c1 is c2
    assert model == settings.OPENROUTER_MODEL
    assert str(c1.base_url).startswith(settings.OPENROUTER_BASE_URL)


def test_follow_up_model_override(monkeypatch, settings):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "FOLLOW_UP_MODEL", "cheap-model")
    assert fug._get_client()[1] == "cheap-model"


async def test_generate_records_usage(monkeypatch):
    content = '<think>x</think>{"follow_ups": [{"label": "Compare", "query": "Compare A and B", "category": "compare"}]}'

    async def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=40, completion_tokens=12),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(fug, "_client", fake)
    monkeypatch.setattr(fug, "_model", "m")
    metrics = RequestMetrics()
    bind_metrics(metrics)
    try:
        items = await fug.generate_follow_ups("q", "answer", ["web_search"])
    finally:
        bind_metrics(None)
    assert [i.label for i in items] == ["Compare"]
    assert (metrics.follow_up_model, metrics.follow_up_input_tokens, metrics.follow_up_output_tokens) == ("m", 40, 12)


def test_openrouter_client_disables_reasoning(monkeypatch, settings):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-or-test")
    fug._get_client()
    assert fug._extra_body == {"reasoning": {"enabled": False}}


def test_openai_client_sends_no_extra_body(monkeypatch, settings):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    fug._get_client()
    assert fug._extra_body is None


async def test_generate_passes_reasoning_off_to_openrouter(monkeypatch):
    seen = {}

    async def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"follow_ups": []}'))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(fug, "_client", fake)
    monkeypatch.setattr(fug, "_model", "m")
    monkeypatch.setattr(fug, "_extra_body", {"reasoning": {"enabled": False}})
    await fug.generate_follow_ups("q", "answer", [])
    assert seen["extra_body"] == {"reasoning": {"enabled": False}}
    assert seen["max_tokens"] == 600


def test_parse_items_truncated_json_returns_empty():
    assert fug._parse_items('{"follow_ups": [{"label": "A", "query": "B", "cat') == []
