"""Multi-Recall Fusion System — BM25 + Embedding + Hot + History fusion.

Implements multi-source recall with configurable weights:
  - BM25 keyword recall: Top 100
  - Embedding vector recall: Top 100
  - Hot Products recall: Top 50
  - History-based recall: Top 50
  → Fusion & dedup → Rerank → Top 10

Weighted scoring: 0.35×BM25 + 0.35×Embedding + 0.20×Hot + 0.10×History

Usage:
    from app.agent.multi_recall import multi_recall

    results = await multi_recall("iPhone 16", entity=entity, top_k=10)
"""

import asyncio
import hashlib
import time
from typing import Optional

from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Recall source weights
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    "bm25": 0.20,
    "embedding": 0.20,
    "hot_products": 0.25,
    "product_cache": 0.20,
    "history": 0.10,
    "live": 0.05,
}

SHOPPING_WEIGHTS = {
    "bm25": 0.15,
    "embedding": 0.15,
    "hot_products": 0.30,
    "product_cache": 0.25,
    "history": 0.10,
    "live": 0.05,
}

TRENDING_WEIGHTS = {
    "bm25": 0.10,
    "embedding": 0.10,
    "hot_products": 0.45,
    "product_cache": 0.25,
    "history": 0.05,
    "live": 0.05,
}


# ═══════════════════════════════════════════════════════════════════════
# Recall sources
# ═══════════════════════════════════════════════════════════════════════

async def _recall_hot_products(query: str, entity=None, top_k: int = 50) -> list[dict]:
    """Recall from hot products database."""
    try:
        from app.agent.hot_products import search_hot_products
        return await search_hot_products(query, top_k=top_k, entity=entity)
    except Exception:
        return []


async def _recall_product_cache(query: str, entity=None, top_k: int = 50) -> list[dict]:
    """Recall from product cache."""
    try:
        from app.agent.product_cache import search_product_cache
        return await search_product_cache(query, top_k=top_k, entity=entity, min_score=0.0)
    except Exception:
        return []


async def _recall_rag(query: str, top_k: int = 50) -> list[dict]:
    """Recall from RAG knowledge base (hybrid BM25+Embedding)."""
    try:
        from rag.hybrid_search import hybrid_search
        docs = await hybrid_search(query, top_k=top_k)
        results = []
        for doc in docs:
            results.append({
                "name": doc.get("content", "")[:100],
                "content": doc.get("content", ""),
                "source": doc.get("source", "rag"),
                "score": doc.get("score", 0.0),
                "recall_source": "rag",
            })
        return results
    except Exception:
        return []


async def _recall_history(user_id: str, top_k: int = 50) -> list[dict]:
    """Recall from user's search/browse history."""
    if not user_id:
        return []
    try:
        from app.cache.redis_cache import get_cache
        cache_layer = await get_cache()
        history = await cache_layer.get(f"eva:history:{user_id}")
        if history and isinstance(history, list):
            return history[:top_k]
        return []
    except Exception:
        return []


async def _recall_live(query: str, user_id: str = "", top_k: int = 20) -> list[dict]:
    """Recall from live e-commerce search."""
    try:
        from app.agent.live_search import live_search_products
        return await live_search_products(query, top_k=min(top_k, 10), user_id=user_id, timeout=4.0)
    except Exception:
        return []


async def _recall_wiki(query: str, top_k: int = 20) -> list[dict]:
    """Recall from product wiki."""
    try:
        from app.agent.product_wiki import search_wiki
        wiki_results = search_wiki(query, top_k=top_k)
        results = []
        for w in wiki_results:
            results.append({
                "name": w["title"],
                "brand": w["brand"],
                "category": w["category"],
                "overview": w.get("overview", ""),
                "source": "product_wiki",
                "recall_source": "wiki",
                "confidence": w.get("relevance", 30.0),
            })
        return results
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════
# Fusion engine
# ═══════════════════════════════════════════════════════════════════════

def _normalize_scores(results: list[dict], score_field: str = "confidence") -> list[dict]:
    """Normalize scores to 0-100 range within a result set."""
    if not results:
        return results
    scores = [r.get(score_field, 0) or 0 for r in results]
    max_s = max(scores) if scores else 1.0
    min_s = min(scores) if scores else 0.0
    score_range = max_s - min_s if max_s > min_s else 1.0

    for r in results:
        raw = r.get(score_field, 0) or 0
        r["norm_score"] = round((raw - min_s) / score_range * 100.0, 1)

    return results


def _dedup_key(product: dict) -> str:
    """Generate a dedup key for a product."""
    name = (product.get("name") or product.get("title", "")).lower().strip()
    platform = (product.get("platform", "")).lower().strip()
    return hashlib.md5(f"{name}|{platform}".encode()).hexdigest()


def _fuse_results(
    recall_sets: dict[str, list[dict]],
    weights: dict[str, float],
    top_k: int = 10,
) -> list[dict]:
    """Fuse multiple recall sets with weighted scoring and dedup."""
    combined: dict[str, dict] = {}  # keyed by dedup key

    for source, results in recall_sets.items():
        weight = weights.get(source, 0.10)
        results = _normalize_scores(results)
        for r in results:
            key = _dedup_key(r)
            norm_score = r.get("norm_score", 50.0)
            weighted_score = norm_score * weight
            r["recall_source"] = source
            r["weighted_score"] = weighted_score

            if key in combined:
                # Accumulate scores from multiple sources
                combined[key]["weighted_score"] += weighted_score
                # Track all recall sources
                existing_sources = combined[key].get("recall_sources", [])
                if source not in existing_sources:
                    existing_sources.append(source)
                    combined[key]["recall_sources"] = existing_sources
                # Keep the higher confidence version
                if r.get("confidence", 0) > combined[key].get("confidence", 0):
                    combined[key] = {**combined[key], **r}
            else:
                r["recall_sources"] = [source]
                combined[key] = dict(r)

    # Sort by weighted score
    sorted_results = sorted(
        combined.values(),
        key=lambda x: (x.get("weighted_score", 0), x.get("confidence", 0)),
        reverse=True,
    )

    # Dedup by title similarity (keep only the best)
    final = []
    seen_titles = []
    for r in sorted_results:
        title = (r.get("name") or r.get("title", "")).lower().strip()
        # Check if too similar to an already-selected result
        is_dup = False
        for seen in seen_titles:
            if title in seen or seen in title:
                is_dup = True
                break
        if not is_dup:
            seen_titles.append(title)
            r["fused_score"] = r.get("weighted_score", 0)
            r["recall_count"] = len(r.get("recall_sources", []))
            final.append(r)

    return final[:top_k]


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

async def multi_recall(
    query: str,
    entity=None,
    user_id: str = "",
    top_k: int = 10,
    weights: dict[str, float] | None = None,
    enable_live: bool = False,
    enable_history: bool = True,
    enable_wiki: bool = True,
    timeout: float = 8.0,
) -> list[dict]:
    """Execute multi-source recall and fusion.

    Args:
        query: User search query
        entity: Optional ProductEntity for constraint filtering
        user_id: User ID for history recall
        top_k: Final number of results
        weights: Source weights override (default: SHOPPING_WEIGHTS)
        enable_live: Include live e-commerce search
        enable_history: Include user history
        enable_wiki: Include product wiki
        timeout: Total timeout for all recall operations

    Returns:
        Fused and reranked list of product dicts
    """
    t_start = time.perf_counter()
    w = weights or SHOPPING_WEIGHTS

    # Execute all recall sources in parallel
    tasks = {
        "hot_products": _recall_hot_products(query, entity=entity, top_k=50),
        "product_cache": _recall_product_cache(query, entity=entity, top_k=50),
        "rag": _recall_rag(query, top_k=30),
    }

    if enable_wiki:
        tasks["wiki"] = _recall_wiki(query, top_k=20)

    if enable_history:
        tasks["history"] = _recall_history(user_id, top_k=30)

    if enable_live:
        tasks["live"] = _recall_live(query, user_id=user_id, top_k=15)

    recall_sets: dict[str, list[dict]] = {}

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks.values(), return_exceptions=True),
            timeout=timeout,
        )
        for (source,), result in zip(tasks.items(), results):
            if isinstance(result, list):
                recall_sets[source] = result
            elif isinstance(result, Exception):
                append_log("WARN", f"Recall source '{source}' failed: {result}")
                recall_sets[source] = []
            else:
                recall_sets[source] = []
    except asyncio.TimeoutError:
        # Use whatever completed
        append_log("WARN", f"Multi-recall timeout after {timeout}s")

    # Fuse
    fused = _fuse_results(recall_sets, w, top_k=top_k)

    total_ms = (time.perf_counter() - t_start) * 1000
    source_counts = {s: len(r) for s, r in recall_sets.items()}
    append_log(
        "INFO",
        f"Multi-recall: {sum(source_counts.values())} candidates from {len(recall_sets)} sources "
        f"→ {len(fused)} fused results ({total_ms:.0f}ms) sources={source_counts}",
    )

    return fused


async def quick_recall(query: str, entity=None, top_k: int = 5) -> list[dict]:
    """Fast multi-recall for quick responses (<1s target)."""
    return await multi_recall(
        query, entity=entity, top_k=top_k,
        weights={"hot_products": 0.55, "product_cache": 0.45},
        enable_live=False, enable_history=False, enable_wiki=False,
        timeout=1.5,
    )


async def deep_recall(query: str, entity=None, user_id: str = "", top_k: int = 10) -> list[dict]:
    """Deep multi-recall for comprehensive results."""
    return await multi_recall(
        query, entity=entity, user_id=user_id, top_k=top_k,
        weights=SHOPPING_WEIGHTS,
        enable_live=True, enable_history=True, enable_wiki=True,
        timeout=12.0,
    )


async def trending_recall(query: str, entity=None, top_k: int = 10) -> list[dict]:
    """Trending-focused recall for trend_analysis intent."""
    return await multi_recall(
        query, entity=entity, top_k=top_k,
        weights=TRENDING_WEIGHTS,
        enable_live=False, enable_history=False, enable_wiki=True,
        timeout=5.0,
    )
