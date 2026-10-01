from research_agent.blocks.block_formatter import ToolResult, format_blocks


def test_financial_cards_from_tools():
    results = [
        ToolResult("get_stock_price", {}, "STOCK|TCS.NS|3500|+1.20%|30|4000|3000\nreadable"),
        ToolResult("get_forex_rate", {}, "FOREX|USD|INR|83.1|2026-10-01"),
        ToolResult("get_crypto_price", {}, "CRYPTO|bitcoin|5000000|60000|-2.00%"),
        ToolResult("get_crypto_price", {}, "Coin 'nope' not found on CoinGecko."),
    ]
    r = format_blocks("Prices.", results, "q")
    cards = [b for b in r.blocks if b.template_id == "insight-cards"][0].data.items
    assert [c.title for c in cards] == ["TCS.NS Stock Price", "USD/INR Exchange Rate", "Bitcoin Price"]
    assert [c.severity for c in cards] == ["success", "info", "warning"]


def test_markdown_financial_fallback():
    text = "| Coin | Price (USD) | 24h Change |\n|---|---|---|\n| Bitcoin | $60,000 | +2% |"
    r = format_blocks(text, [], "q")
    cards = [b for b in r.blocks if b.template_id == "insight-cards"][0].data.items
    assert cards[0].title == "Bitcoin Price"


def test_news_rows_and_sources():
    news = ToolResult("latest_news", {}, "Found 1:\nNEWS|RBI / cut|NDTV|Tue|https://n.com/a")
    search = ToolResult("web_search", {}, "1. **a**\n   b\n   Source: https://a.com/x.\n2. Source: https://a.com/x")
    r = format_blocks("Answer", [news, search], "q")
    table = [b for b in r.blocks if b.template_id == "data-table"][0].data
    assert table.rows == [{"Headline": "RBI / cut", "Source": "NDTV", "Published": "Tue"}]
    assert r.sources == ["https://a.com/x"]
