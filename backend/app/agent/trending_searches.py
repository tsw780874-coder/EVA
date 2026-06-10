"""Trending Search Database — hot search keywords and auto-suggestions.

Maintains a database of trending search queries with:
  - search_count: estimated search volume
  - growth_rate: week-over-week growth trend
  - category: mapped product category
  - entity_match: which ProductEntity this search maps to

Used for:
  1. Auto-complete suggestions
  2. "Hot right now" search recommendations
  3. Query normalization (map trending searches to canonical queries)
  4. Popularity boost in search scoring

Usage:
    from app.agent.trending_searches import get_trending_searches, suggest_searches

    trending = await get_trending_searches(category="smartphone", top_k=10)
    suggestions = await suggest_searches("iPhon", top_k=5)
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field

from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Trending Search Entry
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TrendingSearch:
    """A trending search keyword entry."""
    keyword: str               # The search keyword
    canonical: str = ""        # Canonical/normalized form
    category: str = ""         # Mapped product category
    brand: str = ""            # Detected brand (if any)
    search_count: int = 0      # Estimated search volume
    growth_rate: float = 0.0   # Week-over-week growth (e.g., 0.25 = +25%)
    rank: int = 999            # Current trend rank
    last_updated: float = field(default_factory=time.time)
    source: str = "estimated"  # "scraped" | "estimated" | "manual"
    seasonality: str = ""      # "evergreen" | "seasonal" | "event" | "new_release"

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "canonical": self.canonical or self.keyword,
            "category": self.category,
            "brand": self.brand,
            "search_count": self.search_count,
            "growth_rate": self.growth_rate,
            "rank": self.rank,
            "last_updated": self.last_updated,
            "source": self.source,
            "seasonality": self.seasonality,
        }


# ═══════════════════════════════════════════════════════════════════════
# Trending Search Database — ~80 top trending searches
# ═══════════════════════════════════════════════════════════════════════

_TRENDING_SEARCHES: list[TrendingSearch] = [
    # === SMARTPHONE TRENDING ===
    TrendingSearch("iPhone16", "iPhone 16", "smartphone", "Apple", 120000, 0.35, 1, seasonality="new_release"),
    TrendingSearch("iPhone16 Pro Max", "iPhone 16 Pro Max", "smartphone", "Apple", 95000, 0.28, 2, seasonality="new_release"),
    TrendingSearch("iPhone16 Pro", "iPhone 16 Pro", "smartphone", "Apple", 85000, 0.22, 3, seasonality="new_release"),
    TrendingSearch("iPhone 16 价格", "iPhone 16", "smartphone", "Apple", 72000, 0.40, 4, seasonality="new_release"),
    TrendingSearch("华为Mate70", "HUAWEI Mate 70", "smartphone", "HUAWEI", 88000, 0.15, 5, seasonality="new_release"),
    TrendingSearch("Mate70 Pro", "HUAWEI Mate 70 Pro", "smartphone", "HUAWEI", 76000, 0.18, 6, seasonality="new_release"),
    TrendingSearch("小米15", "Xiaomi 15", "smartphone", "Xiaomi", 82000, 0.20, 7, seasonality="new_release"),
    TrendingSearch("小米15 Ultra", "Xiaomi 15 Ultra", "smartphone", "Xiaomi", 68000, 0.32, 8, seasonality="new_release"),
    TrendingSearch("Galaxy S25", "Galaxy S25 Ultra", "smartphone", "Samsung", 55000, 0.10, 9, seasonality="new_release"),
    TrendingSearch("Pura70", "HUAWEI Pura 70", "smartphone", "HUAWEI", 42000, -0.05, 10),
    TrendingSearch("折叠屏手机", "折叠屏手机", "smartphone", "", 38000, 0.25, 11, seasonality="seasonal"),
    TrendingSearch("性价比手机", "性价比手机", "smartphone", "", 45000, 0.05, 12, seasonality="evergreen"),
    TrendingSearch("拍照手机", "拍照手机", "smartphone", "", 35000, 0.08, 13, seasonality="evergreen"),
    TrendingSearch("iPhone15", "iPhone 15", "smartphone", "Apple", 65000, -0.20, 14, seasonality="seasonal"),

    # === GPU TRENDING ===
    TrendingSearch("RTX5090", "RTX 5090", "graphics_card", "NVIDIA", 98000, 0.55, 1, seasonality="new_release"),
    TrendingSearch("RTX5080", "RTX 5080", "graphics_card", "NVIDIA", 85000, 0.45, 2, seasonality="new_release"),
    TrendingSearch("RTX5070", "RTX 5070 Ti", "graphics_card", "NVIDIA", 78000, 0.50, 3, seasonality="new_release"),
    TrendingSearch("RTX5090价格", "RTX 5090", "graphics_card", "NVIDIA", 62000, 0.60, 4, seasonality="new_release"),
    TrendingSearch("RTX4090", "RTX 4090", "graphics_card", "NVIDIA", 45000, -0.30, 5, seasonality="seasonal"),
    TrendingSearch("5070Ti", "RTX 5070 Ti", "graphics_card", "NVIDIA", 42000, 0.65, 6, seasonality="new_release"),
    TrendingSearch("游戏显卡", "游戏显卡", "graphics_card", "", 35000, 0.10, 7, seasonality="evergreen"),
    TrendingSearch("显卡天梯图", "显卡天梯图", "graphics_card", "", 28000, 0.05, 8, seasonality="evergreen"),
    TrendingSearch("RX7900XTX", "RX 7900 XTX", "graphics_card", "AMD", 18000, -0.15, 9),

    # === LAPTOP TRENDING ===
    TrendingSearch("MacBook Pro M4", "MacBook Pro 14 M4", "laptop", "Apple", 72000, 0.30, 1, seasonality="new_release"),
    TrendingSearch("MacBook Air", "MacBook Air M4", "laptop", "Apple", 65000, 0.15, 2, seasonality="evergreen"),
    TrendingSearch("游戏本推荐", "游戏本推荐", "laptop", "", 58000, 0.12, 3, seasonality="evergreen"),
    TrendingSearch("拯救者", "Lenovo 拯救者", "laptop", "Lenovo", 52000, 0.08, 4, seasonality="evergreen"),
    TrendingSearch("ThinkPad", "ThinkPad X1 Carbon", "laptop", "Lenovo", 35000, 0.02, 5, seasonality="evergreen"),
    TrendingSearch("ROG笔记本", "ROG 游戏本", "laptop", "ASUS", 32000, 0.10, 6),
    TrendingSearch("轻薄本推荐", "轻薄本推荐", "laptop", "", 48000, 0.08, 7, seasonality="evergreen"),
    TrendingSearch("学生笔记本", "学生笔记本", "laptop", "", 42000, 0.25, 8, seasonality="seasonal"),

    # === BADMINTON TRENDING ===
    TrendingSearch("天斧99Pro", "YONEX ASTROX 99 PRO", "badminton_racket", "YONEX", 35000, 0.20, 1, seasonality="evergreen"),
    TrendingSearch("天斧100ZZ", "YONEX ASTROX 100ZZ", "badminton_racket", "YONEX", 42000, 0.28, 2, seasonality="evergreen"),
    TrendingSearch("天斧88D PRO", "YONEX ASTROX 88D PRO", "badminton_racket", "YONEX", 28000, 0.10, 3, seasonality="evergreen"),
    TrendingSearch("弓箭11PRO", "YONEX ARCSABER 11 PRO", "badminton_racket", "YONEX", 32000, 0.15, 4, seasonality="evergreen"),
    TrendingSearch("疾光1000Z", "YONEX NANOFLARE 1000Z", "badminton_racket", "YONEX", 25000, 0.35, 5, seasonality="new_release"),
    TrendingSearch("疾光800", "YONEX NANOFLARE 800 PRO", "badminton_racket", "YONEX", 22000, 0.18, 6),
    TrendingSearch("龙牙之刃", "Victor THRUSTER F", "badminton_racket", "Victor", 20000, 0.08, 7),
    TrendingSearch("雷霆80", "Li-Ning AXFORCE 80", "badminton_racket", "Li-Ning", 18000, 0.12, 8),
    TrendingSearch("雷霆90", "Li-Ning AXFORCE 90", "badminton_racket", "Li-Ning", 15000, 0.25, 9, seasonality="new_release"),
    TrendingSearch("羽毛球拍推荐", "羽毛球拍推荐", "badminton_racket", "", 38000, 0.10, 10, seasonality="evergreen"),
    TrendingSearch("尤尼克斯", "YONEX 羽毛球拍", "badminton_racket", "YONEX", 45000, 0.05, 11, seasonality="evergreen"),
    TrendingSearch("进攻型羽毛球拍", "进攻型羽毛球拍", "badminton_racket", "", 15000, 0.05, 12, seasonality="evergreen"),
    TrendingSearch("AS50羽毛球", "YONEX AEROSENSA 50", "badminton_shuttlecock", "YONEX", 22000, 0.10, 13, seasonality="evergreen"),

    # === HEADPHONE TRENDING ===
    TrendingSearch("AirPods Pro 3", "AirPods Pro 3", "headphone", "Apple", 72000, 0.32, 1, seasonality="new_release"),
    TrendingSearch("降噪耳机", "降噪耳机推荐", "headphone", "", 55000, 0.15, 2, seasonality="evergreen"),
    TrendingSearch("AirPods 4", "AirPods 4", "headphone", "Apple", 48000, 0.10, 3),
    TrendingSearch("WH-1000XM6", "Sony WH-1000XM6", "headphone", "Sony", 32000, 0.28, 4, seasonality="new_release"),
    TrendingSearch("TWS耳机推荐", "TWS耳机推荐", "headphone", "", 28000, 0.08, 5, seasonality="evergreen"),

    # === GAMING CONSOLE TRENDING ===
    TrendingSearch("PS5 Pro", "PlayStation 5 Pro", "gaming_console", "Sony", 65000, 0.18, 1, seasonality="new_release"),
    TrendingSearch("Switch 2", "Nintendo Switch 2", "gaming_console", "Nintendo", 85000, 0.45, 2, seasonality="new_release"),
    TrendingSearch("Switch", "Nintendo Switch", "gaming_console", "Nintendo", 55000, -0.10, 3, seasonality="evergreen"),
    TrendingSearch("PS5", "PlayStation 5", "gaming_console", "Sony", 42000, -0.05, 4, seasonality="evergreen"),

    # === SHOE TRENDING ===
    TrendingSearch("AJ1倒钩", "AJ1 倒钩", "shoe", "Nike", 55000, 0.15, 1, seasonality="evergreen"),
    TrendingSearch("Dunk", "Nike Dunk", "shoe", "Nike", 48000, 0.05, 2, seasonality="evergreen"),
    TrendingSearch("Air Force 1", "Air Force 1", "shoe", "Nike", 52000, 0.02, 3, seasonality="evergreen"),
    TrendingSearch("Samba", "Adidas Samba", "shoe", "Adidas", 42000, -0.10, 4),
    TrendingSearch("球鞋推荐", "球鞋推荐", "shoe", "", 38000, 0.10, 5, seasonality="evergreen"),

    # === TV TRENDING ===
    TrendingSearch("OLED电视", "OLED电视推荐", "tv", "", 32000, 0.12, 1, seasonality="evergreen"),
    TrendingSearch("MiniLED电视", "MiniLED电视", "tv", "", 28000, 0.25, 2, seasonality="seasonal"),
    TrendingSearch("75寸电视", "75寸电视推荐", "tv", "", 25000, 0.08, 3, seasonality="evergreen"),

    # === HOME APPLIANCE TRENDING ===
    TrendingSearch("扫地机器人", "扫地机器人推荐", "home_appliance", "", 45000, 0.10, 1, seasonality="evergreen"),
    TrendingSearch("石头扫地机", "Roborock 扫地机器人", "home_appliance", "Roborock", 32000, 0.18, 2),
    TrendingSearch("空调推荐", "空调推荐", "home_appliance", "", 38000, 0.30, 3, seasonality="seasonal"),
    TrendingSearch("戴森吸尘器", "Dyson 吸尘器", "home_appliance", "Dyson", 28000, 0.05, 4, seasonality="evergreen"),

    # === GENERAL TRENDING ===
    TrendingSearch("618手机推荐", "618手机推荐", "smartphone", "", 95000, 0.80, 1, seasonality="event"),
    TrendingSearch("618必买清单", "618必买清单", "", "", 88000, 0.75, 2, seasonality="event"),
    TrendingSearch("性价比推荐", "性价比推荐", "", "", 42000, 0.10, 3, seasonality="evergreen"),
    TrendingSearch("新品首发", "新品首发", "", "", 35000, 0.15, 4, seasonality="evergreen"),
]


# ═══════════════════════════════════════════════════════════════════════
# Index
# ═══════════════════════════════════════════════════════════════════════

_index_built = False
_keyword_index: dict[str, TrendingSearch] = {}
_category_trends: dict[str, list[TrendingSearch]] = {}


def _build_index():
    global _index_built, _keyword_index, _category_trends
    if _index_built:
        return
    rank = 1
    for t in sorted(_TRENDING_SEARCHES, key=lambda x: x.search_count, reverse=True):
        t.rank = rank
        _keyword_index[t.keyword.lower()] = t
        _category_trends.setdefault(t.category, []).append(t)
        rank += 1
    # Sort category trends
    for cat in _category_trends:
        _category_trends[cat].sort(key=lambda x: x.search_count, reverse=True)
    _index_built = True
    append_log("INFO", f"Trending search index: {len(_TRENDING_SEARCHES)} keywords, "
              f"{len(_category_trends)} categories")


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

async def get_trending_searches(
    category: str = "",
    top_k: int = 10,
) -> list[dict]:
    """Get trending searches, optionally filtered by category."""
    _build_index()

    if category and category in _category_trends:
        entries = _category_trends[category][:top_k]
    elif category:
        # Fuzzy category match
        entries = []
        for cat, trends in _category_trends.items():
            if category in cat or cat in category:
                entries.extend(trends)
        entries.sort(key=lambda x: x.search_count, reverse=True)
        entries = entries[:top_k]
    else:
        entries = sorted(_TRENDING_SEARCHES, key=lambda x: x.search_count, reverse=True)[:top_k]

    # Try Redis cache for fast retrieval
    ck = f"eva:trending:{category or 'all'}:{top_k}"
    try:
        from app.cache.redis_cache import get_cache
        cache_layer = await get_cache()
        cached = await cache_layer.get(ck)
        if cached:
            return cached
    except Exception:
        pass

    results = [e.to_dict() for e in entries]

    # Cache with 6h TTL
    if results:
        try:
            from app.cache.redis_cache import get_cache
            cache_layer = await get_cache()
            await cache_layer.set(ck, results, ttl=21600)
        except Exception:
            pass

    return results


async def suggest_searches(prefix: str, top_k: int = 8) -> list[dict]:
    """Auto-complete suggestions based on search prefix."""
    _build_index()
    prefix_lower = prefix.lower().strip()
    if len(prefix_lower) < 1:
        return await get_trending_searches(top_k=top_k)

    matches: list[TrendingSearch] = []
    for kw, entry in _keyword_index.items():
        if prefix_lower in kw:
            matches.append(entry)
        elif prefix_lower in entry.canonical.lower():
            matches.append(entry)

    matches.sort(key=lambda x: x.search_count, reverse=True)
    return [m.to_dict() for m in matches[:top_k]]


async def lookup_trending(query: str) -> dict | None:
    """Look up a query in trending searches. Returns canonical form if found."""
    _build_index()
    q = query.lower().strip()
    entry = _keyword_index.get(q)
    if entry:
        return entry.to_dict()

    # Fuzzy match
    for kw, entry in _keyword_index.items():
        if kw in q or q in kw:
            return entry.to_dict()
    return None


async def get_trending_categories() -> list[dict]:
    """Get trending categories with aggregated search counts."""
    _build_index()
    result = []
    for cat, entries in _category_trends.items():
        total_searches = sum(e.search_count for e in entries)
        avg_growth = sum(e.growth_rate for e in entries) / max(len(entries), 1)
        result.append({
            "category": cat,
            "total_searches": total_searches,
            "avg_growth_rate": round(avg_growth, 3),
            "keyword_count": len(entries),
            "top_keywords": [e.keyword for e in entries[:3]],
        })
    result.sort(key=lambda x: x["total_searches"], reverse=True)
    return result


async def refresh_trending() -> dict:
    """Refresh trending search data."""
    global _index_built
    _index_built = False
    _build_index()
    try:
        from app.cache.redis_cache import get_cache
        cache_layer = await get_cache()
        await cache_layer.delete("eva:trending:*")
    except Exception:
        pass
    stats = {
        "total_keywords": len(_TRENDING_SEARCHES),
        "categories": len(_category_trends),
        "top_trend": max(_TRENDING_SEARCHES, key=lambda x: x.search_count).keyword,
    }
    append_log("INFO", f"Trending searches refreshed: {stats}")
    return stats
