from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from ..config import get_settings
from .schemas import FollowUp

logger = logging.getLogger(__name__)

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


async def generate_follow_ups(
    query: str,
    final_text: str,
    tool_names: list[str],
) -> list[FollowUp]:
    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        return []

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    user_msg = (
        f"Original query: {query}\n\n"
        f"Tools used: {', '.join(tool_names)}\n\n"
        f"Research answer (first 1500 chars):\n{final_text[:1500]}"
    )

    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.7,
        max_tokens=256,
        response_format={"type": "json_object"},
    )

    raw = json.loads(resp.choices[0].message.content or "{}")
    items = raw.get("follow_ups", [])
    return [
        FollowUp(
            label=item["label"][:40],
            query=item["query"],
            category=item.get("category", "deeper"),
        )
        for item in items
        if isinstance(item, dict) and "label" in item and "query" in item
    ][:3]
