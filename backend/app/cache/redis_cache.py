"""Redis cache wrapper with graceful fallback to in-memory dict.

Usage:
    from app.cache.redis_cache import get_cache

    cache = await get_cache()
    await cache.set("key", "value", ttl=300)
    value = await cache.get("key")
"""

import asyncio
import json
import time
from typing import Any

from app.config import get_settings
from app.api.v1.admin import append_log

# ---------------------------------------------------------------------------
# In-memory fallback (always available)
# ---------------------------------------------------------------------------

_inmem: dict[str, tuple[float, Any]] = {}


def _inmem_set(key: str, value: Any, ttl: int = 300) -> None:
    _inmem[key] = (time.time() + ttl, value)


def _inmem_get(key: str) -> Any | None:
    entry = _inmem.get(key)
    if entry is None:
        return None
    expiry, value = entry
    if time.time() > expiry:
        del _inmem[key]
        return None
    return value


def _inmem_delete(pattern: str = "*") -> int:
    count = 0
    keys = list(_inmem.keys())
    for k in keys:
        if pattern == "*" or pattern in k:
            del _inmem[k]
            count += 1
    return count


# ---------------------------------------------------------------------------
# Redis client (lazy init)
# ---------------------------------------------------------------------------

_redis = None
_redis_available = False
_redis_init_attempted = False


async def _init_redis() -> bool:
    global _redis, _redis_available, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_available
    _redis_init_attempted = True

    try:
        import redis.asyncio as aioredis
        settings = get_settings()
        _redis = await aioredis.from_url(
            settings.redis_url or "redis://localhost:6379/0",
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            socket_keepalive=True,
            decode_responses=True,
            max_connections=20,  # 连接池大小
        )
        await _redis.ping()
        _redis_available = True
        append_log("INFO", "Redis 缓存已连接 (max_connections=20)")
    except Exception:
        _redis_available = False
        append_log("WARN", "Redis 不可用，使用内存缓存")

    return _redis_available


async def get_redis_client():
    """获取原始 Redis 客户端 — 供 memory_service 等模块统一使用。

    所有模块应通过此函数获取 Redis 连接，避免创建多个连接池。
    """
    if await _init_redis():
        return _redis
    return None


# ---------------------------------------------------------------------------
# Public cache API
# ---------------------------------------------------------------------------


class CacheLayer:
    """Unified cache that tries Redis first, falls back to in-memory."""

    async def get(self, key: str) -> Any | None:
        if await _init_redis():
            try:
                raw = await _redis.get(key)
                if raw is not None:
                    return json.loads(raw)
            except Exception:
                pass
        return _inmem_get(key)

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        if await _init_redis():
            try:
                await _redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
            except Exception:
                _inmem_set(key, value, ttl)
        else:
            _inmem_set(key, value, ttl)

    async def delete(self, pattern: str = "*") -> int:
        count = 0
        if await _init_redis():
            try:
                keys = await _redis.keys(pattern)
                if keys:
                    count = await _redis.delete(*keys)
            except Exception:
                pass
        count += _inmem_delete(pattern)
        return count

    async def flush(self) -> bool:
        """Clear all cache."""
        if await _init_redis():
            try:
                await _redis.flushdb()
            except Exception:
                pass
        _inmem.clear()
        return True


# Singleton
_cache: CacheLayer | None = None


async def get_cache() -> CacheLayer:
    global _cache
    if _cache is None:
        _cache = CacheLayer()
    return _cache
