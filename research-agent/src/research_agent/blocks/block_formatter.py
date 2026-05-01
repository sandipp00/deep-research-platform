"""Converts Deep Agent tool results into structured ResearchResponse blocks."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from research_agent.blocks.schemas import (
    Block,
    DataTableBlock,
    DataTableData,
    InsightCardsBlock,
    InsightCardsData,
    InsightItem,
    LeafletMapBlock,
    LeafletMapData,
    MapMarker,
    MarkdownBlock,
    MarkdownData,
    ResearchResponse,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    tool_name: str
    input: dict[str, Any] = field(default_factory=dict)
    output: str = ""


def format_blocks(
    final_text: str,
    tool_results: list[ToolResult],
    query: str,
) -> ResearchResponse:
    blocks: list[Block] = []
    sources: list[str] = []

    # 1. Always: markdown summary block first
    blocks.append(MarkdownBlock(data=MarkdownData(content=final_text.strip())))

    # 2. nearby_places → leaflet-map + data-table
    place_results = [r for r in tool_results if r.tool_name == "nearby_places"]
    if place_results:
        raw = place_results[-1].output
        markers = _parse_places_to_markers(raw)
        rows = _parse_places_to_rows(raw)
        if markers:
            blocks.append(LeafletMapBlock(data=LeafletMapData(
                center={"lat": markers[0].lat, "lon": markers[0].lon},
                zoom=13,
                markers=markers,
            )))
        if rows:
            blocks.append(DataTableBlock(data=DataTableData(
                columns=["Name", "Address", "Distance"],
                rows=rows,
            )))

    # 3. financial tools → insight-cards (only when structured data is present)
    financial = [
        r for r in tool_results
        if r.tool_name in ("get_stock_price", "get_crypto_price", "get_forex_rate")
    ]
    already_has_insight_cards = False
    if financial:
        items = [card for r in financial if (card := _parse_financial_card(r)) is not None]
        if items:
            blocks.append(InsightCardsBlock(data=InsightCardsData(items=items)))
            already_has_insight_cards = True

    # 3b. Fallback: if no financial tool was called but the model produced a
    # markdown table matching a financial shape (columns including Coin/
    # Cryptocurrency/Ticker + Price + Change), synthesize InsightItems from
    # the markdown. Pairs with the prompt-tightening in #40 as belt-and-
    # braces — even if MiniMax routes a crypto/stock query through
    # web_search despite the prompt, the FE still gets its FinancialGrid.
    # Scoped to crypto and stock shapes. #41.
    if not already_has_insight_cards:
        fallback_items = _extract_financial_cards_from_markdown(final_text)
        if fallback_items:
            blocks.append(InsightCardsBlock(data=InsightCardsData(items=fallback_items)))

    # 4. latest_news → data-table
    news_results = [r for r in tool_results if r.tool_name == "latest_news"]
    if news_results:
        rows = _parse_news_to_rows(news_results[-1].output)
        if rows:
            blocks.append(DataTableBlock(data=DataTableData(
                columns=["Headline", "Source", "Published"],
                rows=rows,
            )))

    # 5. Collect source URLs
    for r in tool_results:
        if r.tool_name in ("web_search", "read_webpage"):
            sources.extend(_extract_urls(r.output))

    return ResearchResponse(
        query=query,
        blocks=blocks,
        sources=list(dict.fromkeys(sources)),  # deduplicated, order preserved
    )


# ── Parsers ───────────────────────────────────────────────────

def _parse_places_to_markers(raw: str) -> list[MapMarker]:
    """Parse PLACE|name|lat|lon|address lines."""
    markers = []
    for line in raw.splitlines():
        if not line.startswith("PLACE|"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        try:
            markers.append(MapMarker(
                lat=float(parts[2]),
                lon=float(parts[3]),
                label=parts[1],
                popup=parts[4],
            ))
        except (ValueError, IndexError):
            continue
    return markers


def _parse_places_to_rows(raw: str) -> list[dict]:
    """Parse PLACE lines into table rows."""
    rows = []
    for line in raw.splitlines():
        if not line.startswith("PLACE|"):
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        rows.append({
            "Name": parts[1],
            "Address": parts[4] if len(parts) > 4 else "",
            "Distance": parts[5] if len(parts) > 5 else "",
        })
    return rows


def _parse_financial_card(result: ToolResult) -> InsightItem | None:
    """Parse STOCK|, FOREX|, CRYPTO| lines into an InsightItem.

    Returns None if no structured data is found (e.g. tool returned an error).
    """
    raw = result.output
    try:
        # Find the first structured line in multi-line output
        for line in raw.splitlines():
            line = line.strip()
            if result.tool_name == "get_stock_price" and line.startswith("STOCK|"):
                parts = line.split("|")
                if len(parts) >= 4:
                    symbol, price, change = parts[1], parts[2], parts[3]
                    severity = "success" if not change.startswith("-") else "warning"
                    body_parts = [f"Price: {price}", f"Change: {change}"]
                    if len(parts) > 4 and parts[4]:
                        body_parts.append(f"P/E: {parts[4]}")
                    if len(parts) > 6:
                        body_parts.append(f"52w: {parts[5]} – {parts[6]}")
                    return InsightItem(
                        title=f"{symbol} Stock Price",
                        body=" · ".join(body_parts),
                        severity=severity,
                    )

            elif result.tool_name == "get_forex_rate" and line.startswith("FOREX|"):
                parts = line.split("|")
                if len(parts) >= 5:
                    return InsightItem(
                        title=f"{parts[1]}/{parts[2]} Exchange Rate",
                        body=f"1 {parts[1]} = {parts[3]} {parts[2]} (as of {parts[4]})",
                        severity="info",
                    )

            elif result.tool_name == "get_crypto_price" and line.startswith("CRYPTO|"):
                parts = line.split("|")
                if len(parts) >= 5:
                    change = parts[4]
                    severity = "success" if not change.startswith("-") else "warning"
                    return InsightItem(
                        title=f"{parts[1].capitalize()} Price",
                        body=f"₹{parts[2]} · ${parts[3]} · 24h: {change}",
                        severity=severity,
                    )
    except Exception as e:
        logger.warning("Failed to parse financial card for %s: %s", result.tool_name, e)

    # No structured data found — skip this card
    return None


# ── Markdown fallback parser for financial tables ─────────────
#
# MiniMax-M2.7 sometimes routes crypto/stock queries through web_search
# despite the explicit "use get_crypto_price / get_stock_price" guidance
# in _RESEARCH_SYSTEM_PROMPT (see #40). When it does, no CRYPTO|/STOCK|
# structured line is emitted and _parse_financial_card returns nothing.
# The model instead summarises the prices into a markdown table inside
# its final_text. This fallback parses those tables and synthesises the
# InsightItems _parse_financial_card would have produced, so the FE's
# FinancialGrid renders regardless of which path the agent took.
#
# Intentionally scoped — only crypto-shape and stock-shape tables are
# caught. False positives (a user asking for a comparison chart that
# happens to include a "Price" column) would be rare and degrade
# gracefully to extra grid cards.

_COIN_COLUMN_NAMES = {"coin", "cryptocurrency", "crypto", "token", "asset"}
_STOCK_COLUMN_NAMES = {"ticker", "symbol", "stock", "equity", "company"}
_PRICE_COLUMN_RE = re.compile(r"^price\b", re.IGNORECASE)
_CHANGE_COLUMN_RE = re.compile(r"\b(change|1d|24h|24 hour|change %|%\s*change)\b", re.IGNORECASE)


def _normalise_header(h: str) -> str:
    """Strip markdown emphasis + whitespace from a column header cell."""
    return re.sub(r"[*_`]", "", h).strip()


def _find_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """Return (headers, rows) for every GFM-style table in `text`.

    Tolerates leading/trailing whitespace, optional leading/trailing
    pipes, and an alignment divider row (---|---|---). Skips tables with
    < 1 data row.
    """
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" not in line or i + 1 >= len(lines):
            i += 1
            continue
        divider = lines[i + 1].strip()
        # GFM divider looks like |---|---| or |:---:|:---:| etc.
        if not re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", divider):
            i += 1
            continue
        headers = [_normalise_header(c) for c in line.strip("|").split("|")]
        rows: list[list[str]] = []
        j = i + 2
        while j < len(lines) and "|" in lines[j].strip() and lines[j].strip():
            rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
            j += 1
        if rows:
            tables.append((headers, rows))
        i = j
    return tables


def _pluck_number(cell: str) -> str | None:
    """Extract the first numeric-looking substring from a cell, preserving
    sign and decimal point. Returns None when nothing resembles a number."""
    if not cell:
        return None
    m = re.search(r"[+-]?[\d,]+(?:\.\d+)?", cell)
    return m.group(0).replace(",", "") if m else None


def _classify_table(headers: list[str]) -> str | None:
    """Return 'crypto' | 'stock' | None based on the header names."""
    lower = [h.lower() for h in headers]
    has_coin = any(h in _COIN_COLUMN_NAMES for h in lower)
    has_stock_name = any(h in _STOCK_COLUMN_NAMES for h in lower)
    has_price = any(_PRICE_COLUMN_RE.search(h) for h in lower)
    has_change = any(_CHANGE_COLUMN_RE.search(h) for h in lower)
    if not has_price:
        return None
    if has_coin and has_change:
        return "crypto"
    if has_stock_name and has_change:
        return "stock"
    return None


def _col_index(headers: list[str], predicate) -> int | None:
    for idx, h in enumerate(headers):
        if predicate(h):
            return idx
    return None


def _extract_financial_cards_from_markdown(final_text: str) -> list[InsightItem]:
    """Scan final_text for markdown tables in a crypto or stock shape and
    synthesize one InsightItem per row. Returns [] when nothing matches.
    Mirrors the output of _parse_financial_card as closely as possible
    so FE's isFinancialShape detector matches both paths identically."""
    if not isinstance(final_text, str) or not final_text:
        return []

    items: list[InsightItem] = []
    for headers, rows in _find_markdown_tables(final_text):
        kind = _classify_table(headers)
        if not kind:
            continue

        name_idx = _col_index(
            headers,
            lambda h: h.lower() in (
                _COIN_COLUMN_NAMES if kind == "crypto" else _STOCK_COLUMN_NAMES
            ),
        )
        if name_idx is None:
            continue

        # Separate INR and USD columns when both are present (crypto tables
        # frequently show both). Otherwise pick the first Price column.
        inr_idx = _col_index(headers, lambda h: "inr" in h.lower() and _PRICE_COLUMN_RE.search(h.lower()))
        usd_idx = _col_index(headers, lambda h: "usd" in h.lower() and _PRICE_COLUMN_RE.search(h.lower()))
        price_idx = _col_index(headers, lambda h: _PRICE_COLUMN_RE.search(h.lower())) if inr_idx is None and usd_idx is None else None
        change_idx = _col_index(headers, lambda h: _CHANGE_COLUMN_RE.search(h.lower()))
        pe_idx = _col_index(headers, lambda h: h.lower().strip() in {"p/e", "pe", "p/e ratio"})

        for row in rows:
            if len(row) <= name_idx:
                continue
            name = re.sub(r"\s*\([^)]*\)\s*$", "", row[name_idx]).strip()
            if not name:
                continue

            inr = _pluck_number(row[inr_idx]) if inr_idx is not None and len(row) > inr_idx else None
            usd = _pluck_number(row[usd_idx]) if usd_idx is not None and len(row) > usd_idx else None
            price = _pluck_number(row[price_idx]) if price_idx is not None and len(row) > price_idx else None
            change = row[change_idx].strip() if change_idx is not None and len(row) > change_idx else None
            change_num = _pluck_number(change) if change else None

            if kind == "crypto":
                # Match the CRYPTO| output shape: "₹X · $Y · 24h: change"
                body_parts = []
                if inr: body_parts.append(f"₹{inr}")
                if usd: body_parts.append(f"${usd}")
                if change: body_parts.append(f"24h: {change}")
                if not body_parts:
                    continue
                severity = "success" if not (change_num or "").startswith("-") else "warning"
                items.append(InsightItem(
                    title=f"{name.capitalize()} Price",
                    body=" · ".join(body_parts),
                    severity=severity,
                ))
            else:  # stock
                body_parts = []
                if price: body_parts.append(f"Price: {price}")
                if change: body_parts.append(f"Change: {change}")
                pe = _pluck_number(row[pe_idx]) if pe_idx is not None and len(row) > pe_idx else None
                if pe: body_parts.append(f"P/E: {pe}")
                if not body_parts:
                    continue
                severity = "success" if not (change_num or "").startswith("-") else "warning"
                items.append(InsightItem(
                    title=f"{name} Stock Price",
                    body=" · ".join(body_parts),
                    severity=severity,
                ))

    return items


def _parse_news_to_rows(raw: str) -> list[dict]:
    """Parse NEWS|title|source|published|link lines."""
    rows = []
    for line in raw.splitlines():
        if not line.startswith("NEWS|"):
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        rows.append({
            "Headline": parts[1],
            "Source": parts[2],
            "Published": parts[3],
        })
    return rows[:10]  # cap at 10 headlines


def _extract_urls(output: str) -> list[str]:
    """Extract clean URLs from tool output, stripping trailing punctuation/numbering."""
    raw_urls = re.findall(r"https?://[^\s\)\"'<>]+", output)
    cleaned = []
    for url in raw_urls:
        # Strip trailing punctuation that may be part of surrounding text
        url = re.sub(r"[.,;:!?\\\n]+$", "", url)
        if url and len(url) > 10:
            cleaned.append(url)
    return cleaned
