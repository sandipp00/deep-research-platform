import logging

import redis.asyncio as aioredis

from research_agent.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis: aioredis.Redis | None = None

async def connect_redis() -> None:
    global _redis
    logger.info("Connecting to Redis at %s", settings.REDIS_URL)
    _redis = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis.ping()
    logger.info("Redis connected")


async def disconnect_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
    _redis = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis client not connected")
    return _redis


# ── Tool result cache helpers ─────────────────────────────────

async def cache_get(key: str) -> str | None:
    try:
        r = get_redis()
        return await r.get(key)
    except Exception as e:
        logger.warning("Redis cache_get failed for %s: %s", key, e)
        return None


async def cache_set(key: str, value: str, ttl: int) -> None:
    try:
        r = get_redis()
        await r.set(key, value, ex=ttl)
    except Exception as e:
        logger.warning("Redis cache_set failed for %s: %s", key, e)
