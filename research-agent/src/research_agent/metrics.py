from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("research_agent.metrics")


@dataclass
class ToolRecord:
    name: str
    latency_ms: int
    cache_hit: bool
    success: bool
    provider: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "latency_ms": self.latency_ms,
            "cache_hit": self.cache_hit,
            "success": self.success,
            "provider": self.provider,
        }


@dataclass
class RequestMetrics:
    model: str = ""
    follow_up_model: str = ""
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started: float = field(default_factory=time.perf_counter)
    first_checkpoint_ms: int | None = None
    tool_call_count: int = 0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    follow_up_input_tokens: int = 0
    follow_up_output_tokens: int = 0
    tools: list[ToolRecord] = field(default_factory=list)
    outcome: str = "unknown"
    error: str | None = None
    query_chars: int = 0
    history_messages: int = 0

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def mark_checkpoint(self) -> None:
        if self.first_checkpoint_ms is None:
            self.first_checkpoint_ms = self.elapsed_ms()

    def add_usage(self, usage: Any) -> None:
        if not usage:
            return
        get = usage.get if isinstance(usage, dict) else lambda k, d=0: getattr(usage, k, d)
        inp = int(get("input_tokens", 0) or 0)
        out = int(get("output_tokens", 0) or 0)
        tot = int(get("total_tokens", 0) or 0) or inp + out
        self.llm_calls += 1
        self.input_tokens += inp
        self.output_tokens += out
        self.total_tokens += tot

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "outcome": self.outcome,
            "total_latency_ms": self.elapsed_ms(),
            "first_checkpoint_ms": self.first_checkpoint_ms,
            "model": self.model,
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "follow_up_model": self.follow_up_model,
            "follow_up_input_tokens": self.follow_up_input_tokens,
            "follow_up_output_tokens": self.follow_up_output_tokens,
            "tool_call_count": self.tool_call_count,
            "tools": [t.as_dict() for t in self.tools],
            "search_providers": [t.provider for t in self.tools if t.name == "web_search"],
            "query_chars": self.query_chars,
            "history_messages": self.history_messages,
            "error": self.error,
        }

    def log(self) -> dict[str, Any]:
        data = self.to_dict()
        logger.info(json.dumps({"event": "research_request", **data}, default=str))
        return data


_current: contextvars.ContextVar[RequestMetrics | None] = contextvars.ContextVar(
    "research_metrics", default=None
)


def current_metrics() -> RequestMetrics | None:
    return _current.get()


def bind_metrics(metrics: RequestMetrics | None) -> contextvars.Token:
    return _current.set(metrics)


def record_tool(record: ToolRecord) -> None:
    m = _current.get()
    if m is not None:
        m.tools.append(record)
