"""Maps Deep Agent tool names to user-visible progress messages."""
from __future__ import annotations

import re
from typing import Any


def format_tool_start(tool_name: str, tool_input: dict[str, Any]) -> str:
    match tool_name:
        case "web_search":
            query = tool_input.get("query", "")
            return f'Searching the web for: "{query}"...'
        case "read_webpage":
            url = tool_input.get("url", "")
            domain = _extract_domain(url)
            return f"Reading {domain}..."
        case "wiki_search":
            return "Looking up Wikipedia..."
        case "nearby_places":
            place = tool_input.get("place", "")
            place_type = tool_input.get("place_type", "places")
            return f"Searching for {place_type} near {place}..."
        case "latest_news":
            topic = tool_input.get("topic", "")
            return f'Checking latest news on "{topic}"...'
        case "get_stock_price":
            symbol = tool_input.get("symbol", "")
            return f"Fetching stock price for {symbol}..."
        case "get_forex_rate":
            frm = tool_input.get("from_currency", "")
            to = tool_input.get("to_currency", "")
            return f"Fetching {frm}/{to} exchange rate..."
        case "get_crypto_price":
            coin = tool_input.get("coin_id", "")
            return f"Fetching {coin} price..."
        case "write_todos":
            return "Organizing research plan..."
        case "write_file":
            return "Saving research findings..."
        case "read_file":
            return "Reading research notes..."
        case "task":
            agent = tool_input.get("agent", "specialized agent")
            return f"Delegating to {agent}..."
        case _:
            return f"Running {tool_name}..."


def format_tool_end(tool_name: str, tool_output: str) -> str:
    match tool_name:
        case "web_search":
            count = _count_results(tool_output)
            return f"Found {count} results. Analyzing..."
        case "read_webpage":
            return "Page content retrieved. Analyzing..."
        case "wiki_search":
            return "Found Wikipedia entry. Analyzing..."
        case "nearby_places":
            count = _count_places(tool_output)
            return f"Found {count} nearby locations. Analyzing..."
        case "latest_news":
            count = _count_news(tool_output)
            return f"Got {count} news articles. Analyzing..."
        case "get_stock_price":
            return "Got market data."
        case "get_forex_rate":
            return "Got exchange rate."
        case "get_crypto_price":
            return "Got crypto data."
        case "write_todos":
            return "Research plan ready. Starting..."
        case "task":
            return "Sub-research complete. Synthesizing..."
        case _:
            return ""


# ── Helpers ───────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else url[:40]


def _count_results(output: str) -> int:
    # web_search returns numbered results: "1. **title**..."
    matches = re.findall(r"^\d+\.", output, re.MULTILINE)
    return len(matches) if matches else 1


def _count_places(output: str) -> int:
    return output.count("PLACE|")


def _count_news(output: str) -> int:
    return output.count("NEWS|")
