"""HTTP/SSE handler — runs Deep Agent and streams checkpoints + final blocks."""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
from typing import Any, AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from research_agent.agent.graph import get_agent
from research_agent.consumer.block_formatter import ToolResult, format_blocks
from research_agent.consumer.checkpoint_formatter import format_tool_end, format_tool_start
from research_agent.consumer.follow_up_generator import generate_follow_ups

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)
_CLARIFICATION_PREFIX = "[CLARIFICATION]"


class HistoryEntry(BaseModel):
    role: str
    content: str


class ResearchRequest(BaseModel):
    query: str
    conversation_history: list[HistoryEntry] = Field(default_factory=list)


def _sse(event: str, data: Any) -> str:
    """Format an SSE message. data is JSON-serialized."""
    payload = json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _build_messages(req: ResearchRequest) -> list:
    messages: list = []
    for entry in req.conversation_history:
        if not entry.content:
            continue
        if entry.role == "user":
            messages.append(HumanMessage(content=entry.content))
        elif entry.role in ("assistant", "alvoff"):
            messages.append(AIMessage(content=entry.content))

    today = datetime.datetime.now(datetime.timezone.utc).strftime("%A, %d %B %Y")
    query = f"{req.query}\n\nContext:\nToday's date: {today}"
    messages.append(HumanMessage(content=query))
    return messages


def _extract_text(output) -> str:
    if output is None or not hasattr(output, "content"):
        return ""
    content = output.content
    if isinstance(content, str):
        return _THINK_RE.sub("", content).strip()
    if isinstance(content, list):
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return _THINK_RE.sub("", " ".join(p for p in text_parts if p.strip()).strip()).strip()
    return ""


async def stream_research(req: ResearchRequest) -> AsyncIterator[str]:
    """Run the agent, yield SSE events: checkpoint, blocks/clarification, done, error."""
    yield _sse("checkpoint", {
        "status": "in_progress",
        "content": "Researching your query...",
    })

    try:
        agent = await get_agent()
    except Exception as e:
        logger.exception("Failed to initialize agent")
        yield _sse("error", {"status": "failed", "content": f"Agent init failed: {e}"})
        return

    messages = _build_messages(req)
    final_text = ""
    tool_results: list[ToolResult] = []

    try:
        async for event in agent.astream_events(
            {"messages": messages},
            config={"recursion_limit": 50},
            version="v2",
        ):
            etype = event.get("event", "")

            if etype == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input", {})
                if isinstance(tool_input, str):
                    tool_input = {"query": tool_input}
                msg_text = format_tool_start(tool_name, tool_input)
                if msg_text:
                    yield _sse("checkpoint", {
                        "status": "in_progress",
                        "content": msg_text,
                        "tool": tool_name,
                    })

            elif etype == "on_tool_end":
                tool_name = event.get("name", "")
                raw_output = event.get("data", {}).get("output")
                tool_output = str(raw_output.content) if hasattr(raw_output, "content") else str(raw_output or "")
                tool_input = event.get("data", {}).get("input", {})
                if isinstance(tool_input, str):
                    tool_input = {"query": tool_input}

                tool_results.append(ToolResult(
                    tool_name=tool_name, input=tool_input, output=tool_output,
                ))

                end_msg = format_tool_end(tool_name, tool_output)
                if end_msg:
                    yield _sse("checkpoint", {
                        "status": "in_progress",
                        "content": end_msg,
                        "tool": tool_name,
                    })

            elif etype == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                candidate = _extract_text(output)
                if candidate:
                    final_text = candidate

    except Exception as e:
        logger.exception("Agent stream failed")
        yield _sse("error", {"status": "failed", "content": str(e)})
        return

    if not final_text:
        final_text = "I couldn't find specific information for your query. Please try rephrasing."

    stripped = final_text.strip()
    if stripped.startswith(_CLARIFICATION_PREFIX):
        question = stripped[len(_CLARIFICATION_PREFIX):].strip()
        yield _sse("clarification", {"status": "completed", "content": question})
        yield _sse("done", {"status": "completed"})
        return

    try:
        research_response = format_blocks(final_text, tool_results, req.query)
        try:
            tool_names = list({r.tool_name for r in tool_results})
            follow_ups = await asyncio.wait_for(
                generate_follow_ups(req.query, final_text, tool_names),
                timeout=3.0,
            )
            research_response.follow_ups = follow_ups
        except Exception:
            logger.debug("Follow-up generation skipped")

        yield _sse("blocks", {
            "status": "completed",
            "data": research_response.model_dump(),
        })
    except Exception as e:
        logger.exception("Block formatting failed")
        yield _sse("error", {"status": "failed", "content": f"Block formatting failed: {e}"})
        return

    yield _sse("done", {"status": "completed"})
