"""Popularity Scoring System — weighted multi-signal product scoring.

Implements the scoring formula:
  Final Score = 0.4 × Semantic + 0.3 × Keyword + 0.2 × Popularity + 0.1 × Brand

Usage:
    from app.agent.popularity_scorer import score_results, re_rank

    scored = score_results(query, results, entity=entity)
    re_ranked = re_rank(query, results, entity=entity)
"""

import hashlib
import time
from functools import lru_cache
from typing import Optional

from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Scoring components
# ═══════════════════════════════════════════════════════════════════════

def _semantic_score(query: str, title: str) -> float:
    """Semantic similarity score based on word overlap (0-100)."""
    q = query.lower()
    t = title.lower()

    if q in t or t in q:
        return 100.0

    q_words = set(q.split())
    t_words = set(t.split())
    if not q_words:
        return 0.0

    overlap = q_words & t_words
    return min(len(overlap) / max(len(q_words), 1) * 100.0, 100.0)


def _keyword_score(query: str, product: dict) -> float:
    """Keyword matching score (0-100)."""
    q = query.lower()
    score = 0.0

    brand = (product.get("brand") or "").lower()
    model = (product.get("model") or "").lower()
    category = (product.get("category") or "").lower()
    title = (product.get("title") or product.get("name", "")).lower()

    # Brand match
    if brand and brand in q:
        score += 40.0

    # Model match
    if model:
        model_parts = model.lower().replace("-", " ").replace("_", " ").split()
        for part in model_parts:
            if len(part) > 1 and part in q:
                score += 25.0

    # Number/version match (e.g., "16", "5090")
    import re
    q_nums = set(re.findall(r'\d+', q))
    t_nums = set(re.findall(r'\d+', title))
    if q_nums and t_nums:
        num_overlap = q_nums & t_nums
        score += min(len(num_overlap) * 15.0, 30.0)

    return min(score, 100.0)


def _popularity_score(product: dict) -> float:
    """Extract popularity from product metadata (0-100)."""
    # From hot_products entries
    if "popularity_score" in product:
        return float(product["popularity_score"])

    # From product_cache entries
    rating = float(product.get("rating", 0) or 0)
    review_count = int(product.get("review_count", 0) or 0)

    pop = 50.0  # Default baseline

    # Rating contribution (max 30)
    pop += min(rating * 6.0, 30.0)

    # Review count contribution (max 20)
    if review_count > 100000:
        pop += 20.0
    elif review_count > 50000:
        pop += 15.0
    elif review_count > 10000:
        pop += 10.0
    elif review_count > 1000:
        pop += 5.0

    # Source authority bonus
    source = product.get("source", "")
    if source == "hot_products":
        pop += 10.0
    elif source == "product_cache":
        pop += 5.0

    return min(pop, 100.0)


def _brand_score(query: str, product: dict, entity=None) -> float:
    """Brand match score (0-100)."""
    q = query.lower()
    brand = (product.get("brand") or "").lower()
    title = (product.get("title") or product.get("name", "")).lower()

    score = 0.0

    # Direct brand mention in query
    if brand and brand in q:
        score += 70.0

    # Entity brand match
    if entity and entity.brand:
        entity_brands = {entity.brand.lower()} | {a.lower() for a in (entity.brand_aliases or [])}
        if brand in entity_brands:
            score += 30.0
        else:
            # Check title
            for eb in entity_brands:
                if eb in title:
                    score += 15.0
                    break

    return min(score, 100.0)


# ═══════════════════════════════════════════════════════════════════════
# Entity constraint check
# ═══════════════════════════════════════════════════════════════════════

def _entity_penalty(product: dict, entity) -> float:
    """Return penalty multiplier for entity mismatch. 1.0 = no penalty, 0.0 = reject."""
    if not entity or not entity.is_valid or entity.confidence < 0.4:
        return 1.0

    title = (product.get("title") or product.get("name", "")).lower()
    brand = (product.get("brand") or "").lower()
    category = (product.get("category") or "").lower()

    # Category check
    if entity.category and entity.category != "general" and category:
        from app.agent.product_validator import _are_categories_compatible
        if not _are_categories_compatible(entity.category, category):
            return 0.0  # Reject

    # Brand check
    if entity.brand and entity.confidence >= 0.6 and brand:
        entity_brands = {entity.brand.lower()} | {a.lower() for a in (entity.brand_aliases or [])}
        if brand not in entity_brands:
            name_has_brand = any(b in title for b in entity_brands)
            if not name_has_brand:
                return 0.1  # Heavy penalty but not full rejection (could be a variant)

    return 1.0


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def score_product(
    query: str,
    product: dict,
    entity=None,
) -> float:
    """Score a single product with the weighted formula.

    Final = 0.4 × Semantic + 0.3 × Keyword + 0.2 × Popularity + 0.1 × Brand
    """
    penalty = _entity_penalty(product, entity)
    if penalty == 0.0:
        return 0.0

    title = product.get("title") or product.get("name", "")
    if not title:
        return 0.0

    semantic = _semantic_score(query, title)
    keyword = _keyword_score(query, product)
    popularity = _popularity_score(product)
    brand = _brand_score(query, product, entity)

    raw = 0.4 * semantic + 0.3 * keyword + 0.2 * popularity + 0.1 * brand

    # Apply entity penalty
    final = raw * penalty

    # Log for debugging high-confidence misses
    if final > 70:
        pass  # Good match

    return round(final, 1)


def score_results(
    query: str,
    results: list[dict],
    entity=None,
) -> list[tuple[float, dict]]:
    """Score all results, returning (score, product) tuples sorted by score desc."""
    scored = []
    for r in results:
        s = score_product(query, r, entity=entity)
        if s > 0:
            scored.append((s, dict(r)))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def re_rank(
    query: str,
    results: list[dict],
    entity=None,
    top_k: int = 5,
) -> list[dict]:
    """Re-rank search results using the full scoring formula.

    Integrates:
      - Semantic similarity
      - Keyword matching
      - Popularity boosting
      - Brand matching
      - Entity constraint filtering
    """
    if not results:
        return []

    scored = score_results(query, results, entity=entity)

    # Deduplicate by title
    seen: set[str] = set()
    final: list[dict] = []
    for score, r in scored:
        title = (r.get("title") or r.get("name", "")).lower().strip()
        if title not in seen:
            seen.add(title)
            r["final_score"] = score
            r["confidence"] = min(score * 0.9, 98.0)
            final.append(r)

    result = final[:top_k]

    if result:
        scores = [r["final_score"] for r in result]
        append_log(
            "DEBUG",
            f"Re-rank: {len(result)} results, scores={[round(s,1) for s in scores[:5]]}",
        )

    return result


def compute_popularity_trend(
    current_count: int,
    previous_count: int,
    days_between: int = 7,
) -> float:
    """Compute week-over-week growth rate."""
    if previous_count == 0:
        return 1.0 if current_count > 0 else 0.0
    return round((current_count - previous_count) / previous_count, 3)


@lru_cache(maxsize=256)
def normalize_search_query(query: str) -> str:
    """Normalize a search query to its canonical form using trending data."""
    # Check if query matches a trending keyword's canonical form
    import asyncio
    q = query.lower().strip()
    # Simple normalization: strip excessive whitespace, common prefixes
    prefixes = ["想买", "我要买", "帮我找", "搜索", "查找", "推荐一个", "有没有"]
    for prefix in prefixes:
        if q.startswith(prefix):
            q = q[len(prefix):].strip()
            break

    suffixes = ["多少钱", "价格", "报价", "哪里买", "在哪买", "推荐", "哪个好"]
    for suffix in suffixes:
        if q.endswith(suffix):
            q = q[:-len(suffix)].strip()
            break

    return q
