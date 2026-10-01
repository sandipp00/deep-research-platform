import logging
from urllib.parse import urlsplit, urlunsplit

import redis.asyncio as aioredis

from research_agent.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_redis: aioredis.Redis | None = None


def mask_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid url>"
    if parts.password is None and parts.username is None:
        return url
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    user = parts.username or ""
    netloc = f"{user}:***@{host}" if parts.password is not None else f"{user}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


async def connect_redis() -> None:
    global _redis
    logger.info("Connecting to Redis at %s", mask_url(settings.REDIS_URL))
    try:
        _redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await _redis.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis unavailable, continuing without cache: %s", type(e).__name__)


async def disconnect_redis() -> None:
    global _redis
    if _redis:
        try:
            await _redis.aclose()
        except Exception:
            logger.warning("Redis close failed")
    _redis = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis client not connected")
    return _redis


async def cache_get(key: str) -> str | None:
    try:
        return await get_redis().get(key)
    except Exception as e:
        logger.warning("Redis cache_get failed for %s: %s", key, type(e).__name__)
        return None


async def cache_set(key: str, value: str, ttl: int) -> None:
    try:
        await get_redis().set(key, value, ex=ttl)
    except Exception as e:
        logger.warning("Redis cache_set failed for %s: %s", key, type(e).__name__)
