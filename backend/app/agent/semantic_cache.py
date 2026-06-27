"""EVA Semantic Cache Engine v2.0 — 语义级缓存加速器

核心优化：同类查询一次搜索，永久复用。

Strategy:
  Level 1: Exact match (SHA256) → <1ms lookup
  Level 2: Normalized match (keyword normalization) → <5ms lookup
  Level 3: Category match (同类目缓存) → <10ms lookup

Cache TTL: 10 min exact, 5 min semantic, 3 min category
Storage: Redis (primary) + In-memory (fallback)

Usage:
    from app.agent.semantic_cache import semantic_cache
    result = await semantic_cache.get("我要买一件西装")
    if result:
        return result  # <10ms response!
"""

import asyncio
import hashlib
import time
from functools import lru_cache

from app.api.v1.admin import append_log

# ═══════════════════════════════════════════════════════════════════════
# Cache storage
# ═══════════════════════════════════════════════════════════════════════

_memory_cache: dict[str, tuple[float, dict]] = {}  # key → (expiry, result)
_EXACT_TTL = 600    # 10 min
_SEMANTIC_TTL = 300 # 5 min
_CATEGORY_TTL = 180 # 3 min


def _exact_key(query: str) -> str:
    """SHA256 exact match key."""
    return f"exact:{hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]}"


def _normalize_query(query: str) -> str:
    """Normalize query for semantic matching.

    Removes filler words, normalizes synonyms.
    """
    import re
    q = query.strip().lower()
    # Remove filler words
    for word in ["我要", "我想", "帮我", "请问", "能不能", "可以", "吗", "呢", "吧", "一下", "一个", "一双", "一件"]:
        q = q.replace(word, " ")
    # Normalize synonyms
    synonyms = {
        "西装": "西服", "西服": "西服", "正装": "西服",
        "篮球鞋": "篮球鞋", "球鞋": "运动鞋",
        "手机": "手机", "电话": "手机",
        "耳机": "耳机", "耳塞": "耳机",
        "笔记本": "笔记本", "笔记本电脑": "笔记本", "电脑": "笔记本",
    }
    for old, new in synonyms.items():
        q = q.replace(old, new)
    # Collapse whitespace
    q = re.sub(r'\s+', ' ', q).strip()
    return q


def _semantic_key(query: str) -> str:
    """Semantic (normalized) cache key."""
    norm = _normalize_query(query)
    return f"sem:{hashlib.sha256(norm.encode()).hexdigest()[:16]}"


def _category_key(query: str) -> str:
    """Category-level cache key."""
    from app.agent.category_mapper import map_category
    cat = map_category(query)
    if cat.is_valid:
        return f"cat:{cat.primary}:{cat.subcategory}"
    return ""


# ═══════════════════════════════════════════════════════════════════════
# Cache API
# ═══════════════════════════════════════════════════════════════════════


class SemanticCache:
    """语义缓存引擎 — 三级缓存加速。"""

    def __init__(self):
        self.hits = 0
        self.misses = 0

    async def get(self, query: str) -> dict | None:
        """Try to get cached result for query.

        Returns None if cache miss (must run full pipeline).
        """
        now = time.time()
        keys = [_exact_key(query), _semantic_key(query), _category_key(query)]

        for key in keys:
            if not key:
                continue
            # In-memory check
            if key in _memory_cache:
                expiry, result = _memory_cache[key]
                if now < expiry:
                    self.hits += 1
                    result["_cache_hit"] = True
                    result["_cache_level"] = key.split(":")[0]
                    result["_cache_age_ms"] = (now - (expiry - self._ttl_for(key))) * 1000
                    append_log("INFO", f"SemanticCache HIT: {key} ({query[:30]}...)")
                    return dict(result)  # Return copy
                else:
                    del _memory_cache[key]

            # Redis check
            try:
                from app.cache.redis_cache import get_cache
                cache_layer = await get_cache()
                cached = await cache_layer.get(f"eva:sc:{key}")
                if cached and now < cached.get("expiry", 0):
                    self.hits += 1
                    result = cached.get("result", {})
                    result["_cache_hit"] = True
                    result["_cache_level"] = key.split(":")[0]
                    append_log("INFO", f"SemanticCache REDIS HIT: {key}")
                    # Populate memory
                    _memory_cache[key] = (cached["expiry"], result)
                    return dict(result)
            except Exception:
                pass

        self.misses += 1
        return None

    async def set(self, query: str, result: dict) -> None:
        """Store pipeline result in cache."""
        now = time.time()
        # Store at exact key (10 min)
        ek = _exact_key(query)
        _memory_cache[ek] = (now + _EXACT_TTL, result)
        # Store at semantic key (5 min) if normalized differs
        sk = _semantic_key(query)
        if sk != ek:
            _memory_cache[sk] = (now + _SEMANTIC_TTL, result)
        # Store at category key (3 min)
        ck = _category_key(query)
        if ck:
            _memory_cache[ck] = (now + _CATEGORY_TTL, result)

        # Redis (fire-and-forget)
        try:
            from app.cache.redis_cache import get_cache
            cache_layer = await get_cache()
            await cache_layer.set(
                f"eva:sc:{ek}",
                {"expiry": now + _EXACT_TTL, "result": result},
                ttl=_EXACT_TTL,
            )
        except Exception:
            pass

    def _ttl_for(self, key: str) -> int:
        if key.startswith("exact:"):
            return _EXACT_TTL
        if key.startswith("sem:"):
            return _SEMANTIC_TTL
        return _CATEGORY_TTL

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def clear(self) -> None:
        """Clear all in-memory caches (new session)."""
        _memory_cache.clear()


# Singleton
semantic_cache = SemanticCache()
