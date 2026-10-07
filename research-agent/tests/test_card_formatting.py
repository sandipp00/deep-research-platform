import pytest

from research_agent.blocks.block_formatter import (
    ToolResult,
    _parse_financial_card,
    format_blocks,
    format_money,
    format_percent,
    format_rate,
)


def _card(tool, output):
    return _parse_financial_card(ToolResult(tool, {}, output))


@pytest.mark.parametrize("raw,expected", [
    ("8066707", "₹80,66,707"),
    (8066707.4, "₹80,66,707"),
    ("123456789", "₹12,34,56,789"),
    ("99999", "₹99,999.00"),
    ("3500.5", "₹3,500.50"),
    ("950", "₹950.00"),
])
def test_inr_indian_grouping(raw, expected):
    assert format_money(raw, "INR") == expected


@pytest.mark.parametrize("raw,expected", [
    ("83856", "$83,856.00"),
    ("1234567.891", "$1,234,567.89"),
    ("60000", "$60,000.00"),
    ("-1500", "-$1,500.00"),
])
def test_large_usd(raw, expected):
    assert format_money(raw, "USD") == expected


@pytest.mark.parametrize("raw,expected", [
    ("0.00001234", "$0.00001234"),
    ("1.234e-05", "$0.00001234"),
    ("0.5", "$0.50"),
    ("0.0823", "$0.0823"),
])
def test_small_crypto_prices_keep_precision(raw, expected):
    assert format_money(raw, "USD") == expected


def test_unknown_currency_uses_code_and_no_currency_is_plain():
    assert format_money("1234.5", "CHF") == "CHF 1,234.50"
    assert format_money("1234.5") == "1,234.50"


@pytest.mark.parametrize("raw,expected", [
    ("+1.2%", "+1.20%"),
    ("-2%", "-2.00%"),
    ("3.456", "+3.46%"),
    (0, "+0.00%"),
    ("-0.004%", "-0.00%"),
])
def test_percent_sign_and_two_decimals(raw, expected):
    assert format_percent(raw) == expected


@pytest.mark.parametrize("raw", ["", "N/A", None, "nan", " "])
def test_missing_values_return_none(raw):
    assert format_money(raw, "USD") is None
    assert format_percent(raw) is None
    assert format_rate(raw) is None


def test_forex_rate_trims_zeros():
    assert format_rate("83.1") == "83.10"
    assert format_rate("0.01203") == "0.01203"
    assert format_rate("1.08765") == "1.0877"


def test_crypto_card_body():
    card = _card("get_crypto_price", "CRYPTO|bitcoin|8066707|83856|+1.5%")
    assert card.body == "₹80,66,707 · $83,856.00 · 24h: +1.50%"
    assert card.severity == "success"


def test_crypto_card_small_price_and_missing_inr():
    card = _card("get_crypto_price", "CRYPTO|pepe|N/A|0.00001234|-3.10%")
    assert card.body == "$0.00001234 · 24h: -3.10%"
    assert card.severity == "warning"


def test_crypto_card_all_missing_is_dropped():
    assert _card("get_crypto_price", "CRYPTO|x|N/A|N/A|") is None


def test_indian_stock_card_uses_rupee():
    out = "STOCK|TCS.NS|3500.5|+1.20%|30.456|4000|3000\nTata (TCS.NS)\nCurrent Price: ₹3500.5\n"
    card = _card("get_stock_price", out)
    assert card.body == "Price: ₹3,500.50 · Change: +1.20% · P/E: 30.46 · 52w: ₹4,000.00 – ₹3,000.00"


def test_us_stock_card_uses_reported_currency():
    out = "STOCK|AAPL|227.5|-0.5%|||\nApple (AAPL)\nCurrent Price: USD 227.5\n"
    card = _card("get_stock_price", out)
    assert card.body == "Price: $227.50 · Change: -0.50%"
    assert card.severity == "warning"


def test_stock_symbol_fallback_without_readable_line():
    assert _card("get_stock_price", "STOCK|RELIANCE.NS|2950|+0.1%").body.startswith("Price: ₹2,950.00")
    assert _card("get_stock_price", "STOCK|XYZ|2950|+0.1%").body.startswith("Price: 2,950.00")


def test_forex_card_body():
    card = _card("get_forex_rate", "FOREX|USD|INR|83.1|2026-10-01")
    assert card.body == "1 USD = 83.10 INR (as of 2026-10-01)"


def test_markdown_fallback_formats_numbers():
    text = "| Coin | Price (INR) | Price (USD) | 24h Change |\n|---|---|---|---|\n| Bitcoin | 8066707 | 83856 | -2% |"
    cards = [b for b in format_blocks(text, [], "q").blocks if b.template_id == "insight-cards"][0].data.items
    assert cards[0].body == "₹80,66,707 · $83,856.00 · 24h: -2.00%"
    assert cards[0].severity == "warning"
