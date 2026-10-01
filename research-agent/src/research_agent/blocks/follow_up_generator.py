from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from ..config import get_settings
from ..metrics import current_metrics
from .schemas import FollowUp

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)

_SYSTEM = """\
You generate follow-up suggestions for a research assistant. Given the user's \
original query and the research answer, produce 2-3 follow-up questions the \
user might want to ask next.

Each follow-up must have:
- "label": button text, ≤40 characters
- "query": a complete, self-contained question (not a fragment)
- "category": one of "deeper", "compare", "action", "flip", "fresh"

Categories:
- deeper: drill into a specific finding from the answer
- compare: compare with competitors, alternatives, or benchmarks
- action: bridge to another action like "email me a summary" or "add to calendar"
- flip: look at the opposite perspective or a related angle
- fresh: a lateral but relevant new direction

Rules:
- Respond in the SAME language as the original query
- Each query must stand alone — the user will send it as a brand new message
- Vary the categories — don't repeat the same one
- Return a JSON object with a single key "follow_ups" containing the array

Example output:
{"follow_ups": [
  {"label": "Compare with Ethereum", "query": "Compare Bitcoin and Ethereum prices and 7-day trends", "category": "compare"},
  {"label": "Why the price drop?", "query": "Why did Bitcoin price drop in the last 24 hours?", "category": "deeper"},
  {"label": "Email me this summary", "query": "Email me a summary of the current Bitcoin price and trends", "category": "action"}
]}"""

_client: AsyncOpenAI | None = None
_model: str = ""
_extra_body: dict | None = None


def _get_client() -> tuple[AsyncOpenAI | None, str]:
    global _client, _model, _extra_body
    if _client is not None:
        return _client, _model
    settings = get_settings()
    if settings.OPENROUTER_API_KEY:
        _client = AsyncOpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=15,
            max_retries=1,
        )
        _model = settings.FOLLOW_UP_MODEL or settings.OPENROUTER_MODEL
        _extra_body = {"reasoning": {"enabled": False}}
    elif settings.OPENAI_API_KEY:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=15, max_retries=1)
        _model = settings.FOLLOW_UP_MODEL or "gpt-4o-mini"
    return _client, _model


def reset_client() -> None:
    global _client, _model, _extra_body
    _client = None
    _model = ""
    _extra_body = None


async def generate_follow_ups(
    query: str,
    final_text: str,
    tool_names: list[str],
) -> list[FollowUp]:
    client, model = _get_client()
    if client is None:
        return []

    metrics = current_metrics()
    if metrics is not None:
        metrics.follow_up_model = model

    user_msg = (
        f"Original query: {query}\n\n"
        f"Tools used: {', '.join(tool_names)}\n\n"
        f"Research answer (first 1500 chars):\n{final_text[:1500]}"
    )

    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=600,
        **({"extra_body": _extra_body} if _extra_body else {}),
    )

    usage = getattr(resp, "usage", None)
    if metrics is not None and usage is not None:
        metrics.follow_up_input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        metrics.follow_up_output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)

    items = _parse_items(resp.choices[0].message.content or "")
    if not items:
        logger.warning("Follow-up model returned no parseable items")
    return [
        FollowUp(
            label=str(item["label"])[:40],
            query=str(item["query"]),
            category=str(item.get("category", "deeper")),
        )
        for item in items
        if isinstance(item, dict) and "label" in item and "query" in item
    ][:3]


def _parse_items(content: str) -> list:
    content = _THINK_RE.sub("", content)
    m = re.search(r"\{.*\}|\[.*\]", content, flags=re.DOTALL)
    if not m:
        return []
    try:
        raw = json.loads(m.group(0))
    except ValueError:
        return []
    if isinstance(raw, dict):
        raw = raw.get("follow_ups", [])
    return raw if isinstance(raw, list) else []
