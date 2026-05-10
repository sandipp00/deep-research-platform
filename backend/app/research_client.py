"""Streams SSE events from the research-agent service."""
from collections.abc import AsyncIterator

import httpx

from .config import settings


class AgentEvent:
    __slots__ = ("name", "data")

    def __init__(self, name: str, data: str) -> None:
        self.name = name
        self.data = data


async def stream_research(
    query: str, history: list[dict[str, str]]
) -> AsyncIterator[AgentEvent]:
    """Yield each complete SSE event from the agent (event:/data: pair)."""
    body = {"query": query, "conversation_history": history}
    timeout = httpx.Timeout(connect=15.0, read=600.0, write=30.0, pool=15.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{settings.research_agent_url}/research",
            json=body,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            if resp.status_code // 100 != 2:
                body_text = await resp.aread()
                raise RuntimeError(
                    f"Research agent returned {resp.status_code}: {body_text.decode(errors='replace')}"
                )

            current_event: str | None = None
            data_lines: list[str] = []

            async for raw_line in resp.aiter_lines():
                if raw_line == "":
                    if current_event and data_lines:
                        yield AgentEvent(current_event, "\n".join(data_lines))
                    current_event = None
                    data_lines = []
                elif raw_line.startswith("event: "):
                    current_event = raw_line[7:].strip()
                elif raw_line.startswith("data: "):
                    data_lines.append(raw_line[6:])
                # ignore comments and other lines

            if current_event and data_lines:
                yield AgentEvent(current_event, "\n".join(data_lines))
