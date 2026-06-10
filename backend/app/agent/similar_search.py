"""Similar Product Search — progressive query degradation for maximum recall.

When exact product search fails, this module progressively broadens the search:
  Level 0: Exact query (already tried)
  Level 1: Remove attributes (color, storage, condition)
  Level 2: Remove edition/trim (OC, Ultra, Pro, Max → base model)
  Level 3: Brand + model core (iPhone 16 Pro Max → iPhone 16)
  Level 4: Brand + category (iPhone 16 → Apple 手机)
  Level 5: Category only (Apple 手机 → 智能手机)

At each level, it searches the product cache and returns the best match.
The goal is: at least 1 real product should ALWAYS be findable.

Usage:
    from app.agent.similar_search import similar_product_search

    results = await similar_product_search("RTX5090冰龙OC版 白色")
"""

import asyncio
import hashlib
import time
from functools import lru_cache

from app.agent.query_rewriter import degrade_query, rewrite_query, extract_search_keywords
from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Product similarity scoring
# ═══════════════════════════════════════════════════════════════════════

def _similarity_score(query: str, product_name: str) -> float:
    """Calculate keyword overlap similarity between query and product name."""
    q_words = set(query.lower().split())
    p_words = set(product_name.lower().split())

    if not q_words:
        return 0.0

    # Exact substring match
    if query.lower() in product_name.lower() or product_name.lower() in query.lower():
        base = 50.0
    else:
        base = 0.0

    # Word overlap
    overlap = q_words & p_words
    overlap_score = len(overlap) / max(len(q_words), 1) * 40.0

    # Number/version match bonus
    q_nums = {w for w in q_words if any(c.isdigit() for c in w)}
    p_nums = {w for w in p_words if any(c.isdigit() for c in w)}
    num_overlap = q_nums & p_nums
    num_bonus = min(len(num_overlap) * 10.0, 20.0)

    return base + overlap_score + num_bonus


def _brand_model_similarity(query: str, product: dict) -> float:
    """Score a product against query considering brand and model consistency."""
    score = 0.0
    name = product.get("name", "").lower()
    brand = product.get("brand", "").lower()
    model = product.get("model", "").lower()
    q = query.lower()

    # Brand match
    if brand and brand in q:
        score += 30.0
    elif brand and any(part in q for part in brand.split()):
        score += 15.0

    # Model match
    if model:
        model_parts = model.replace("-", " ").replace("_", " ").split()
        matched_parts = sum(1 for p in model_parts if p in q)
        if matched_parts > 0:
            score += min(matched_parts * 10.0, 25.0)

    # Name overlap
    name_words = set(name.split())
    query_words = set(q.split())
    overlap = name_words & query_words
    score += min(len(overlap) * 5.0, 20.0)

    # Platform trust bonus (京东/天猫 are more reliable)
    if product.get("platform") in ("京东", "天猫"):
        score += 5.0

    return score


# ═══════════════════════════════════════════════════════════════════════
# Multi-source similar search
# ═══════════════════════════════════════════════════════════════════════

async def _search_all_sources(
    query: str,
    top_k: int = 5,
    user_id: str = "",
) -> list[dict]:
    """Search across ALL available sources for a given query."""
    results: list[dict] = []

    # Source 1: Product cache
    try:
        from app.agent.product_cache import search_product_cache
        cache_results = await search_product_cache(query, top_k=top_k)
        for r in cache_results:
            r["search_layer"] = "product_cache"
        results.extend(cache_results)
    except Exception:
        pass

    # Source 2: RAG (try again with expanded query)
    try:
        from app.agent.pipeline import rag_search_products
        rag_prods, _ = await rag_search_products(query, top_k=top_k)
        for r in rag_prods:
            r["search_layer"] = "rag_retry"
        results.extend(rag_prods)
    except Exception:
        pass

    # Source 3: Database
    try:
        from app.core.verifier import DataVerifier
        verifier = DataVerifier()
        db_results = await verifier._search_db(query)
        for r in db_results:
            r["search_layer"] = "database"
            r["confidence"] = 60.0
        results.extend(db_results)
    except Exception:
        pass

    return results


# ═══════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════

async def similar_product_search(
    query: str,
    user_id: str = "",
    max_per_level: int = 5,
    total_timeout: float = 12.0,
    entity=None,  # Optional ProductEntity for category-constrained degradation
) -> list[dict]:
    """Progressive degradation search — find similar products at any cost.

    When entity is provided, degradation is CONSTRAINED to the same category
    group — never cross into unrelated categories (e.g., badminton → phone).

    Algorithm:
      1. Generate degraded query variants (Level 0→5)
      2. For each variant, search all sources
      3. Score results by brand/model/category consistency
      4. Return best matches, ensuring at least 1 result if possible

    Args:
        query: Original user query
        user_id: User ID for tracking
        max_per_level: Max results to collect per degradation level
        total_timeout: Total time budget
        entity: Optional ProductEntity for category-constrained search

    Returns:
        List of product dicts sorted by relevance/confidence
    """
    t_start = time.perf_counter()
    expanded = rewrite_query(query)
    degraded = degrade_query(query)
    has_entity = entity and entity.is_valid and entity.confidence >= 0.4

    all_results: dict[str, dict] = {}  # keyed by content hash for dedup

    def _add_result(r: dict, level: int):
        """Add a result with deduplication, keeping highest confidence."""
        key = hashlib.md5(
            (r.get("name", r.get("title", "")) + r.get("platform", "")).encode()
        ).hexdigest()
        r["degradation_level"] = level

        # Entity-aware scoring
        brand_score = _brand_model_similarity(query, r)
        level_penalty = level * 8.0
        r["similarity_score"] = round(brand_score, 1)
        raw_conf = r.get("confidence", 30.0)

        # HEAVY penalty for cross-category results when entity is known
        if has_entity and entity.category and entity.category != "general":
            result_cat = (r.get("category") or "").lower()
            if result_cat and result_cat != entity.category:
                from app.agent.product_validator import _are_categories_compatible
                if not _are_categories_compatible(entity.category, result_cat):
                    raw_conf -= 200.0  # Effectively reject cross-category

        # Brand penalty for wrong brand
        if has_entity and entity.brand:
            result_brand = (r.get("brand") or "").lower()
            allowed_brands = {entity.brand.lower()} | {a.lower() for a in (entity.brand_aliases or [])}
            if result_brand and result_brand not in allowed_brands:
                raw_conf -= 100.0  # Heavy penalty for wrong brand

        r["confidence"] = max(5.0, min(raw_conf, 95.0) - level_penalty)

        if key in all_results:
            existing = all_results[key]
            if r["confidence"] > existing.get("confidence", 0):
                all_results[key] = r
        else:
            all_results[key] = r

    # Search at each degradation level
    for variant, level in degraded:
        elapsed = time.perf_counter() - t_start
        if elapsed > total_timeout:
            break

        # Stop early if we have enough confident results
        confident = [r for r in all_results.values() if r.get("confidence", 0) >= 60]
        if len(confident) >= max_per_level:
            break

        try:
            results = await asyncio.wait_for(
                _search_all_sources(variant, top_k=max_per_level, user_id=user_id),
                timeout=min(3.0, total_timeout - elapsed),
            )
            for r in results:
                _add_result(r, level)
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue

    # Sort: confidence DESC, degradation level ASC
    sorted_results = sorted(
        all_results.values(),
        key=lambda r: (
            r.get("confidence", 0),
            -r.get("degradation_level", 0),
            r.get("similarity_score", 0),
        ),
        reverse=True,
    )

    # Ensure we return at least something
    if not sorted_results:
        # Ultimate fallback: same category products
        try:
            if has_entity and entity.category and entity.category != "general":
                from app.agent.product_cache import search_by_category
                cat_results = await search_by_category(entity.category, top_k=5)
            else:
                from app.agent.product_cache import search_by_category
                cat_results = await search_by_category(expanded.category, top_k=5)
            for r in cat_results:
                r["degradation_level"] = 5
                r["confidence"] = 15.0
                r["search_layer"] = "category_fallback"
            sorted_results = cat_results
        except Exception:
            pass

    # Filter: only keep results with positive confidence (cross-category penalized to negative)
    final = [r for r in sorted_results if r.get("confidence", 0) > 0][:max_per_level]
    total_ms = (time.perf_counter() - t_start) * 1000

    if final:
        levels_used = sorted(set(r.get("degradation_level", 0) for r in final))
        append_log(
            "SUCCESS",
            f"Similar search: {len(final)} results for '{query[:40]}' "
            f"(degradation levels: {levels_used}, {total_ms:.0f}ms)",
        )
    else:
        append_log("WARN", f"Similar search: NO results for '{query[:40]}' ({total_ms:.0f}ms)")

    return final


async def find_at_least_one(
    query: str,
    user_id: str = "",
    timeout: float = 15.0,
) -> list[dict]:
    """Guaranteed best-effort search — always tries to return at least 1 product.

    This is the safety net. It will try every possible avenue before giving up.
    """
    # Quick cache check first
    try:
        from app.agent.product_cache import search_product_cache
        cache_results = await search_product_cache(query, top_k=3, min_score=5.0)
        if cache_results:
            return cache_results
    except Exception:
        pass

    # Full similar search
    results = await similar_product_search(query, user_id=user_id, total_timeout=timeout)
    if results:
        return results

    # Last resort: brand-level search
    expanded = rewrite_query(query)
    if expanded.brands:
        try:
            from app.agent.product_cache import search_by_brand
            for brand in expanded.brands:
                brand_results = await search_by_brand(brand, top_k=3)
                if brand_results:
                    for r in brand_results:
                        r["confidence"] = 10.0
                        r["degradation_level"] = 4
                        r["search_layer"] = "brand_fallback"
                    return brand_results
        except Exception:
            pass

    # Ultimate ultimate: category search
    try:
        from app.agent.product_cache import search_by_category
        cat_results = await search_by_category(expanded.category, top_k=3)
        if cat_results:
            for r in cat_results:
                r["confidence"] = 5.0
                r["degradation_level"] = 5
                r["search_layer"] = "ultimate_fallback"
            return cat_results
    except Exception:
        pass

    return []
