from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import re
from typing import Any, AsyncIterator, Awaitable, Callable

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field, field_validator

from research_agent.agent.graph import get_agent
from research_agent.blocks.block_formatter import ToolResult, format_blocks
from research_agent.blocks.checkpoint_formatter import format_tool_end, format_tool_start
from research_agent.blocks.follow_up_generator import generate_follow_ups
from research_agent.config import get_settings
from research_agent.metrics import RequestMetrics, bind_metrics

logger = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)
_CLARIFICATION_PREFIX = "[CLARIFICATION]"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), "IST")

GENERIC_ERROR = "Something went wrong while researching your query. Please try again."
TIMEOUT_ERROR = "The research took too long and was stopped. Please try a narrower question."
STEP_LIMIT_ERROR = "The research needed too many steps and was stopped. Please try a narrower question."

Emit = Callable[[str, dict[str, Any]], Awaitable[None]]


class HistoryEntry(BaseModel):
    role: str = Field(max_length=32)
    content: str

    @field_validator("content")
    @classmethod
    def _content_len(cls, v: str) -> str:
        limit = get_settings().MAX_HISTORY_MESSAGE_CHARS
        if len(v) > limit:
            raise ValueError(f"history message exceeds {limit} characters")
        return v


class ResearchRequest(BaseModel):
    query: str
    conversation_history: list[HistoryEntry] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def _query_len(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query must not be empty")
        limit = get_settings().MAX_QUERY_CHARS
        if len(v) > limit:
            raise ValueError(f"query exceeds {limit} characters")
        return v

    @field_validator("conversation_history")
    @classmethod
    def _history_len(cls, v: list[HistoryEntry]) -> list[HistoryEntry]:
        limit = get_settings().MAX_HISTORY_MESSAGES
        if len(v) > limit:
            raise ValueError(f"conversation_history exceeds {limit} messages")
        return v


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def today_ist() -> str:
    return datetime.datetime.now(IST).strftime("%A, %d %B %Y")


def _build_messages(req: ResearchRequest) -> list:
    messages: list = []
    for entry in req.conversation_history:
        if not entry.content:
            continue
        if entry.role == "user":
            messages.append(HumanMessage(content=entry.content))
        elif entry.role in ("assistant", "alvoff"):
            messages.append(AIMessage(content=entry.content))
    messages.append(HumanMessage(content=f"{req.query}\n\nContext:\nToday's date: {today_ist()}"))
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


def _tool_input(event: dict) -> dict:
    tool_input = event.get("data", {}).get("input", {})
    if isinstance(tool_input, str):
        return {"query": tool_input}
    return tool_input if isinstance(tool_input, dict) else {}


async def _run_agent(req: ResearchRequest, emit: Emit, metrics: RequestMetrics) -> None:
    bind_metrics(metrics)
    settings = get_settings()

    try:
        agent = await get_agent()
    except Exception:
        logger.exception("Failed to initialize agent")
        metrics.outcome, metrics.error = "error", "agent_init"
        await emit("error", {"status": "failed", "content": GENERIC_ERROR})
        return

    final_text = ""
    tool_results: list[ToolResult] = []

    try:
        async for event in agent.astream_events(
            {"messages": _build_messages(req)},
            config={"recursion_limit": settings.AGENT_RECURSION_LIMIT},
            version="v2",
        ):
            etype = event.get("event", "")
            if etype == "on_tool_start":
                metrics.tool_call_count += 1
                tool_name = event.get("name", "")
                msg_text = format_tool_start(tool_name, _tool_input(event))
                if msg_text:
                    metrics.mark_checkpoint()
                    await emit("checkpoint", {"status": "in_progress", "content": msg_text, "tool": tool_name})
            elif etype == "on_tool_end":
                tool_name = event.get("name", "")
                raw_output = event.get("data", {}).get("output")
                tool_output = str(raw_output.content) if hasattr(raw_output, "content") else str(raw_output or "")
                tool_results.append(ToolResult(tool_name=tool_name, input=_tool_input(event), output=tool_output))
                end_msg = format_tool_end(tool_name, tool_output)
                if end_msg:
                    await emit("checkpoint", {"status": "in_progress", "content": end_msg, "tool": tool_name})
            elif etype == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                metrics.add_usage(getattr(output, "usage_metadata", None))
                candidate = _extract_text(output)
                if candidate:
                    final_text = candidate
    except GraphRecursionError:
        logger.warning("Agent hit recursion limit %d", settings.AGENT_RECURSION_LIMIT)
        metrics.outcome, metrics.error = "error", "recursion_limit"
        await emit("error", {"status": "failed", "content": STEP_LIMIT_ERROR})
        return
    except Exception as e:
        logger.exception("Agent stream failed")
        metrics.outcome, metrics.error = "error", type(e).__name__
        await emit("error", {"status": "failed", "content": GENERIC_ERROR})
        return

    if not final_text:
        final_text = "I couldn't find specific information for your query. Please try rephrasing."

    stripped = final_text.strip()
    if stripped.startswith(_CLARIFICATION_PREFIX):
        metrics.outcome = "clarification"
        await emit("clarification", {"status": "completed", "content": stripped[len(_CLARIFICATION_PREFIX):].strip()})
        return

    try:
        research_response = format_blocks(final_text, tool_results, req.query)
    except Exception as e:
        logger.exception("Block formatting failed")
        metrics.outcome, metrics.error = "error", type(e).__name__
        await emit("error", {"status": "failed", "content": GENERIC_ERROR})
        return

    try:
        tool_names = list(dict.fromkeys(r.tool_name for r in tool_results))
        research_response.follow_ups = await asyncio.wait_for(
            generate_follow_ups(req.query, final_text, tool_names), timeout=20.0
        )
    except Exception as e:
        logger.warning("Follow-up generation failed: %r", e)

    metrics.outcome = "completed"
    await emit("blocks", {"status": "completed", "data": research_response.model_dump()})


async def stream_research(req: ResearchRequest) -> AsyncIterator[str]:
    settings = get_settings()
    metrics = RequestMetrics(
        model=settings.agent_model_name,
        query_chars=len(req.query),
        history_messages=len(req.conversation_history),
    )
    queue: asyncio.Queue[tuple[str, dict[str, Any]] | None] = asyncio.Queue()

    async def emit(event: str, data: dict[str, Any]) -> None:
        await queue.put((event, data))

    async def producer() -> None:
        try:
            await _run_agent(req, emit, metrics)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Research pipeline failed")
            metrics.outcome, metrics.error = "error", type(e).__name__
            await emit("error", {"status": "failed", "content": GENERIC_ERROR})
        finally:
            queue.put_nowait(None)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + settings.REQUEST_TIMEOUT_SECONDS
    task = asyncio.create_task(producer())
    logged = False
    try:
        yield _sse("checkpoint", {"status": "in_progress", "content": "Researching your query..."})
        timed_out = False
        while True:
            remaining = deadline - loop.time()
            try:
                if remaining <= 0:
                    raise TimeoutError
                item = await asyncio.wait_for(queue.get(), timeout=remaining)
            except (TimeoutError, asyncio.TimeoutError):
                timed_out = True
                break
            if item is None:
                break
            yield _sse(*item)

        if timed_out:
            await _cancel(task)
            metrics.outcome, metrics.error = "timeout", "request_timeout"
            yield _sse("error", {"status": "failed", "content": TIMEOUT_ERROR})

        status = "completed" if metrics.outcome in ("completed", "clarification") else "failed"
        payload = metrics.log()
        logged = True
        yield _sse("done", {"status": status, "metrics": payload})
    finally:
        await _cancel(task)
        if not logged:
            if metrics.outcome in ("unknown", "completed", "clarification"):
                metrics.outcome = "cancelled"
            metrics.log()


async def _cancel(task: asyncio.Task) -> None:
    if task.done():
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
