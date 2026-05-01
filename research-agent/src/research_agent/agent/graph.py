"""Deep Agent singleton — created once on first use, reused for all requests."""
from __future__ import annotations

import asyncio
import logging

from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from research_agent.agent.tools import (
    get_crypto_price,
    get_forex_rate,
    get_stock_price,
    latest_news,
    nearby_places,
    read_webpage,
    web_search,
    wiki_search,
)
from research_agent.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_agent: CompiledStateGraph | None = None
_agent_lock = asyncio.Lock()

_RESEARCH_SYSTEM_PROMPT = """You are Alvoff's research capability — an AI executive assistant for busy Indian professionals.

You handle open-ended queries requiring real-world information:
- Local search: nearest fuel stations, EV chargers, hospitals, pharmacies, ATMs
- Financial: stock prices, currency conversion, crypto rates, market news
- News: RBI policy, GST updates, budget announcements, industry news
- Research: competitor analysis, market landscape, regulatory documents
- General: weather, product comparisons, government schemes, factual queries

## Tool Usage Guidelines
- Use web_search for most queries — always prefer real data over your prior knowledge
- Use latest_news for time-sensitive news (articles from the last few hours)
- **NEVER call read_webpage on news article URLs.** Search snippets are sufficient for news queries. Only call read_webpage for PDFs, government documents, or when the user explicitly asks for the full content of a specific URL.
- **ALWAYS use get_stock_price / get_forex_rate / get_crypto_price for financial data.**
  NEVER use web_search for a price lookup. Those tools return structured output
  that renders as interactive cards; web_search returns prose that collapses to
  a flat markdown table — worse UX, harder to scan. If the user asks for multiple
  symbols, call the relevant tool ONCE PER SYMBOL so the response carries one
  card per item:
    - "Bitcoin and Ethereum prices" → two get_crypto_price calls (bitcoin, ethereum)
    - "AAPL, NVDA, TSLA stock prices" → three get_stock_price calls
    - "USD to INR and EUR to INR" → two get_forex_rate calls
  Do NOT batch them into a single web_search.
- Use nearby_places for "nearest X" queries — it uses GPS coordinates for precision
- Use wiki_search for definitions, overviews, historical facts, concepts
- Use read_webpage when you need the full content of a specific URL or PDF
- For complex multi-step research: use write_todos to plan steps first

## Response Guidelines
- Lead with the most useful information
- Keep responses under 400 words unless a detailed report is explicitly requested
- Cite source URLs for verifiable claims
- Respond in the same language the user used (Hindi, Tamil, Kannada, Telugu, etc.)
- For "find nearby X": always include name, address, and source
- For financial data: always include the data freshness / timestamp
- Be direct — no filler phrases like "Great question!" or "Certainly!"

## Follow-up Questions
- Ask a follow-up ONLY when a critical detail is missing and cannot be inferred (e.g. no ticker for stock price, no location for nearby search, no topic for news)
- Ask at most ONE short question — no lists, no multiple questions
- Do NOT call any tool before asking — return the question immediately as your response
- Do NOT ask if the answer is already visible in the conversation history
- Do NOT ask for details you can reasonably assume or look up (prefer attempting the search with a reasonable assumption)
- When asking a follow-up, your ENTIRE response must be exactly: [CLARIFICATION] followed by the question — nothing else
- Example: [CLARIFICATION] Which city are you searching in?
"""


async def get_agent() -> CompiledStateGraph:
    global _agent
    async with _agent_lock:
        if _agent is None:
            logger.info("Initializing Deep Agent")
            model = _build_model()
            try:
                from deepagents import create_deep_agent
            except ImportError as e:
                raise RuntimeError(
                    "deepagents package not found. Run: uv sync"
                ) from e

            _agent = create_deep_agent(
                model=model,
                system_prompt=_RESEARCH_SYSTEM_PROMPT,
                tools=[
                    web_search,
                    read_webpage,
                    wiki_search,
                    nearby_places,
                    latest_news,
                    get_stock_price,
                    get_forex_rate,
                    get_crypto_price,
                ],
            )
            logger.info("Deep Agent initialized")
    return _agent


def _build_model() -> ChatOpenAI:
    if settings.OPENROUTER_API_KEY:
        logger.info("Using OpenRouter model: %s", settings.OPENROUTER_MODEL)
        return ChatOpenAI(
            model=settings.OPENROUTER_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=4096,
            model_kwargs={
                "parallel_tool_calls": True,
                "extra_body": {"cache_control": {"type": "ephemeral"}},
            },
        )

    if settings.OPENAI_API_KEY:
        logger.info("Using OpenAI fallback model: %s", settings.OPENAI_MODEL)
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=4096,
            model_kwargs={"parallel_tool_calls": True},
        )

    raise RuntimeError(
        "No LLM API key configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY in .env"
    )
