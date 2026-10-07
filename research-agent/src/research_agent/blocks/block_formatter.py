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

    answer_places, clean_text = extract_places(final_text)
    blocks.append(MarkdownBlock(data=MarkdownData(content=clean_text.strip())))

    places = answer_places
    if not places:
        place_results = [r for r in tool_results if r.tool_name == "nearby_places"]
        if place_results:
            places = parse_place_lines(place_results[-1].output)
    if places:
        blocks.append(LeafletMapBlock(data=_build_map_data(places)))
        blocks.append(DataTableBlock(data=DataTableData(
            columns=["Name", "Address", "Distance"] if any(p.distance for p in places)
            else ["Name", "Address"],
            rows=[p.as_row() for p in places],
        )))

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

    if not already_has_insight_cards:
        fallback_items = _extract_financial_cards_from_markdown(final_text)
        if fallback_items:
            blocks.append(InsightCardsBlock(data=InsightCardsData(items=fallback_items)))

    news_results = [r for r in tool_results if r.tool_name == "latest_news"]
    if news_results:
        rows = _parse_news_to_rows(news_results[-1].output)
        if rows:
            blocks.append(DataTableBlock(data=DataTableData(
                columns=["Headline", "Source", "Published"],
                rows=rows,
            )))

    for r in tool_results:
        if r.tool_name in ("web_search", "read_webpage"):
            sources.extend(_extract_urls(r.output))

    return ResearchResponse(
        query=query,
        blocks=blocks,
        sources=list(dict.fromkeys(sources)),
    )


@dataclass
class Place:
    name: str
    lat: float
    lon: float
    address: str = ""
    distance: str = ""

    def as_row(self) -> dict:
        row = {"Name": self.name, "Address": self.address}
        if self.distance:
            row["Distance"] = self.distance
        return row


def _clean_cell(s: str) -> str:
    return re.sub(r"[*_`]", "", s).strip()


def parse_place_line(line: str) -> Place | None:
    line = line.strip().lstrip("-*• ").strip()
    if not line.startswith("PLACE|"):
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 4:
        return None
    name = _clean_cell(parts[1])
    try:
        lat, lon = float(parts[2]), float(parts[3])
    except ValueError:
        return None
    if not name or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    if lat != lat or lon != lon:
        return None
    return Place(
        name=name, lat=lat, lon=lon,
        address=_clean_cell(parts[4]) if len(parts) > 4 else "",
        distance=parts[5] if len(parts) > 5 else "",
    )


def parse_place_lines(raw: str) -> list[Place]:
    places = []
    for line in raw.splitlines():
        p = parse_place_line(line)
        if p:
            places.append(p)
    return places


def extract_places(text: str) -> tuple[list[Place], str]:
    places: list[Place] = []
    kept: list[str] = []
    for line in text.splitlines():
        if line.strip().lstrip("-*• ").strip().startswith("PLACE|"):
            p = parse_place_line(line)
            if p:
                places.append(p)
            continue
        kept.append(line)
    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return places, clean


def _zoom_for_span(span_deg: float) -> int:
    for limit, z in ((0.005, 16), (0.02, 15), (0.05, 14), (0.1, 13), (0.25, 12),
                     (0.5, 11), (1, 10), (2, 9), (5, 7), (10, 6), (30, 4)):
        if span_deg <= limit:
            return z
    return 2


def _build_map_data(places: list[Place]) -> LeafletMapData:
    lats = [p.lat for p in places]
    lons = [p.lon for p in places]
    span = max(max(lats) - min(lats), max(lons) - min(lons))
    return LeafletMapData(
        center={"lat": (max(lats) + min(lats)) / 2, "lon": (max(lons) + min(lons)) / 2},
        zoom=_zoom_for_span(span * 1.3),
        markers=[MapMarker(lat=p.lat, lon=p.lon, label=p.name, popup=p.address) for p in places],
    )


_CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
_INR_SUFFIXES = (".NS", ".BO")
_INR_INDICES = {"^NSEI", "^BSESN", "^NSEBANK"}
_MISSING = {"", "n/a", "na", "none", "null", "nan", "-", "—"}
_PRICE_CURRENCY_RE = re.compile(r"Current Price:\s*(₹|[A-Z]{3}\s)")
_SIMPLE_PERCENT_RE = re.compile(r"^\s*[+-]?[\d,]*\.?\d+\s*%\s*$")


def _to_float(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = re.sub(r"[₹$€£¥,%\s]", "", str(raw))
        if text.lower() in _MISSING:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _decimals_for(value: float, base: int = 2) -> int:
    magnitude = abs(value)
    if magnitude == 0 or magnitude >= 1:
        return base
    digits = base
    while digits < 12 and magnitude * (10 ** digits) < 1000:
        digits += 1
    return digits


def _indian_group(int_digits: str) -> str:
    if len(int_digits) <= 3:
        return int_digits
    head, tail = int_digits[:-3], int_digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def format_number(value: float, decimals: int = 2, indian: bool = False) -> str:
    text = f"{abs(value):.{decimals}f}"
    int_part, _, frac = text.partition(".")
    if len(frac) > 2:
        frac = frac.rstrip("0").ljust(2, "0")
    sign = "-" if value < 0 and (int(int_part) or int(frac or "0")) else ""
    grouped = _indian_group(int_part) if indian else f"{int(int_part):,}"
    return f"{sign}{grouped}.{frac}" if frac else f"{sign}{grouped}"


def format_money(raw: Any, currency: str = "") -> str | None:
    value = _to_float(raw)
    if value is None:
        text = str(raw).strip() if raw is not None else ""
        return None if text.lower() in _MISSING else text
    code = currency.upper()
    if code == "INR":
        decimals = 0 if abs(value) >= 100000 else _decimals_for(value)
        number = format_number(value, decimals, indian=True)
    else:
        number = format_number(value, _decimals_for(value))
    if not code:
        return number
    symbol = _CURRENCY_SYMBOLS.get(code)
    if symbol is None:
        return f"{code} {number}"
    if number.startswith("-"):
        return f"-{symbol}{number[1:]}"
    return f"{symbol}{number}"


def format_percent(raw: Any) -> str | None:
    value = _to_float(raw)
    if value is None:
        text = str(raw).strip() if raw is not None else ""
        return None if text.lower() in _MISSING else text
    return f"{value:+.2f}%"


def format_rate(raw: Any) -> str | None:
    value = _to_float(raw)
    if value is None:
        text = str(raw).strip() if raw is not None else ""
        return None if text.lower() in _MISSING else text
    return format_number(value, _decimals_for(value, 4))


def _stock_currency(symbol: str, raw_output: str) -> str:
    m = _PRICE_CURRENCY_RE.search(raw_output)
    if m:
        token = m.group(1).strip()
        return "INR" if token == "₹" else token
    upper = symbol.upper()
    if upper.endswith(_INR_SUFFIXES) or upper in _INR_INDICES:
        return "INR"
    return ""


def _severity_for(change: Any) -> str:
    value = _to_float(change)
    if value is None:
        return "success" if not str(change or "").strip().startswith("-") else "warning"
    return "warning" if value < 0 else "success"


def _parse_financial_card(result: ToolResult) -> InsightItem | None:
    raw = result.output
    try:
        for line in raw.splitlines():
            line = line.strip()
            if result.tool_name == "get_stock_price" and line.startswith("STOCK|"):
                parts = line.split("|")
                if len(parts) >= 4:
                    symbol = parts[1]
                    currency = _stock_currency(symbol, raw)
                    body_parts = []
                    price = format_money(parts[2], currency)
                    if price:
                        body_parts.append(f"Price: {price}")
                    change = format_percent(parts[3])
                    if change:
                        body_parts.append(f"Change: {change}")
                    if len(parts) > 4:
                        pe_value = _to_float(parts[4])
                        if pe_value is not None:
                            body_parts.append(f"P/E: {format_number(pe_value)}")
                    if len(parts) > 6:
                        high = format_money(parts[5], currency)
                        low = format_money(parts[6], currency)
                        if high and low:
                            body_parts.append(f"52w: {high} – {low}")
                    if not body_parts:
                        return None
                    return InsightItem(
                        title=f"{symbol} Stock Price",
                        body=" · ".join(body_parts),
                        severity=_severity_for(parts[3]),
                    )

            elif result.tool_name == "get_forex_rate" and line.startswith("FOREX|"):
                parts = line.split("|")
                if len(parts) >= 5:
                    rate = format_rate(parts[3])
                    if not rate:
                        return None
                    return InsightItem(
                        title=f"{parts[1]}/{parts[2]} Exchange Rate",
                        body=f"1 {parts[1]} = {rate} {parts[2]} (as of {parts[4]})",
                        severity="info",
                    )

            elif result.tool_name == "get_crypto_price" and line.startswith("CRYPTO|"):
                parts = line.split("|")
                if len(parts) >= 5:
                    body_parts = []
                    inr = format_money(parts[2], "INR")
                    if inr:
                        body_parts.append(inr)
                    usd = format_money(parts[3], "USD")
                    if usd:
                        body_parts.append(usd)
                    change = format_percent(parts[4])
                    if change:
                        body_parts.append(f"24h: {change}")
                    if not body_parts:
                        return None
                    return InsightItem(
                        title=f"{parts[1].capitalize()} Price",
                        body=" · ".join(body_parts),
                        severity=_severity_for(parts[4]),
                    )
    except Exception as e:
        logger.warning("Failed to parse financial card for %s: %s", result.tool_name, e)

    return None


_COIN_COLUMN_NAMES = {"coin", "cryptocurrency", "crypto", "token", "asset"}
_STOCK_COLUMN_NAMES = {"ticker", "symbol", "stock", "equity", "company"}
_PRICE_COLUMN_RE = re.compile(r"^price\b", re.IGNORECASE)
_CHANGE_COLUMN_RE = re.compile(r"\b(change|1d|24h|24 hour|change %|%\s*change)\b", re.IGNORECASE)


def _normalise_header(h: str) -> str:
    return re.sub(r"[*_`]", "", h).strip()


def _find_markdown_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "|" not in line or i + 1 >= len(lines):
            i += 1
            continue
        divider = lines[i + 1].strip()
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
    if not cell:
        return None
    m = re.search(r"[+-]?[\d,]+(?:\.\d+)?", cell)
    return m.group(0).replace(",", "") if m else None


def _classify_table(headers: list[str]) -> str | None:
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


def _card_change(cell: str) -> str:
    if _SIMPLE_PERCENT_RE.match(cell):
        return format_percent(cell) or cell
    return cell


def _extract_financial_cards_from_markdown(final_text: str) -> list[InsightItem]:
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
                body_parts = []
                if inr: body_parts.append(format_money(inr, "INR"))
                if usd: body_parts.append(format_money(usd, "USD"))
                if change: body_parts.append(f"24h: {_card_change(change)}")
                if not body_parts:
                    continue
                severity = "success" if not (change_num or "").startswith("-") else "warning"
                items.append(InsightItem(
                    title=f"{name.capitalize()} Price",
                    body=" · ".join(body_parts),
                    severity=severity,
                ))
            else:
                body_parts = []
                if price: body_parts.append(f"Price: {format_money(price)}")
                if change: body_parts.append(f"Change: {_card_change(change)}")
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
    return rows[:10]


def _extract_urls(output: str) -> list[str]:
    raw_urls = re.findall(r"https?://[^\s\)\"'<>]+", output)
    cleaned = []
    for url in raw_urls:
        url = re.sub(r"[.,;:!?\\\n]+$", "", url)
        if url and len(url) > 10:
            cleaned.append(url)
    return cleaned
