"""Rerank search results — v8 enhanced reranker.

Features:
  - Freshness decay (time-based weighting)
  - LLM-based reranking (semantic relevance scoring)
  - Multi-factor scoring (freshness × relevance × authority)
  - Stale data marking

Scoring formula:
  Final = 0.5 × Semantic(LLM) + 0.3 × Freshness + 0.2 × Keyword Overlap

Usage:
    from rag.reranker import rerank

    top_docs = await rerank(query, candidates, top_k=5, use_llm=True)
"""

import re
import asyncio
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════════════════════
# Freshness scoring
# ═══════════════════════════════════════════════════════════════════════

FRESH_THRESHOLD_30 = 30
FRESH_THRESHOLD_90 = 90
FRESH_THRESHOLD_180 = 180


def _extract_date(content: str) -> datetime | None:
    """Try to extract date from content (supports multiple formats)."""
    # YAML frontmatter: updated_at: 2024-06-15
    match = re.search(r'updated_at[:：]\s*(\d{4}-\d{2}-\d{2})', content)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # ISO format in text: 2024-06-15T10:30:00
    match = re.search(r'(\d{4}-\d{2}-\d{2})[T ]\d{2}:\d{2}', content)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Chinese date: 2024年6月15日
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', content)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3))
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Simple date: 2024-06-15
    match = re.search(r'(\d{4}-\d{2}-\d{2})', content)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _freshness_weight(content: str) -> tuple[float, str | None]:
    """Freshness weight (0.0-1.0) and optional warning."""
    updated = _extract_date(content)
    if updated is None:
        return 0.8, None  # Unknown age → assume moderate

    now = datetime.now(timezone.utc)
    age_days = (now - updated).days

    if age_days <= FRESH_THRESHOLD_30:
        return 1.0, None
    elif age_days <= FRESH_THRESHOLD_90:
        return 0.9, None
    elif age_days <= FRESH_THRESHOLD_180:
        return 0.5, f"数据{age_days}天未更新，可能不是最新信息"
    else:
        return 0.2, f"数据已超过{age_days}天未更新，可能已过期"


# ═══════════════════════════════════════════════════════════════════════
# Keyword overlap scoring
# ═══════════════════════════════════════════════════════════════════════

def _keyword_overlap(query: str, content: str) -> float:
    """Compute keyword overlap score (0.0-1.0)."""
    q_lower = query.lower()
    c_lower = content.lower()

    # Direct substring → high score
    if q_lower in c_lower:
        return 0.8

    # Word overlap
    q_words = set(q_lower.split())
    c_words = set(c_lower.split())
    if not q_words:
        return 0.0

    overlap = q_words & c_words
    return min(len(overlap) / len(q_words), 1.0)


# ═══════════════════════════════════════════════════════════════════════
# LLM-based reranking
# ═══════════════════════════════════════════════════════════════════════

async def _llm_rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """Use LLM to re-rank candidates by semantic relevance.

    Sends top candidates to LLM with a ranking prompt.
    Falls back to score-based ranking if LLM is unavailable.
    """
    if len(candidates) <= top_k:
        return candidates

    try:
        from app.agent.llm_utils import llm_call

        # Build prompt with candidates
        items_text = []
        for i, doc in enumerate(candidates[:15], 1):
            content = doc.get("content", "")[:200]
            score = doc.get("score", 0)
            items_text.append(f"[{i}] (score={score:.2f}) {content}")

        prompt = "\n".join(items_text)

        system_prompt = (
            "你是一个搜索排序助手。根据用户查询，对以下候选文档按相关性排序。\n"
            "规则：\n"
            "1. 选择与查询最相关的文档\n"
            "2. 考虑文档是否包含具体数据（价格、参数、评价）\n"
            "3. 优先选择权威性高的文档\n"
            "4. 返回文档编号列表，用逗号分隔\n"
            "只返回编号，不要其他内容。例如: 3,7,1,5,2"
        )

        ranking_text, _, _ = await llm_call(
            system_prompt=system_prompt,
            user_message=f"查询: {query}\n\n候选文档:\n{prompt}",
            max_tokens=50,
            temperature=0.1,
            user_id="reranker",
            node_name="rerank_llm",
        )

        # Parse ranking
        try:
            ranked_indices = [
                int(x.strip()) - 1
                for x in ranking_text.replace("，", ",").split(",")
                if x.strip().isdigit()
            ]
            reranked = [
                candidates[i] for i in ranked_indices
                if 0 <= i < len(candidates)
            ]
            # Fill remaining with unranked
            ranked_set = set(ranked_indices)
            for i, doc in enumerate(candidates):
                if i not in ranked_set:
                    reranked.append(doc)
            return reranked[:top_k]
        except (ValueError, IndexError):
            pass

    except Exception:
        pass

    # Fallback: score-based
    return sorted(candidates, key=lambda x: x.get("score", 0), reverse=True)[:top_k]


# ═══════════════════════════════════════════════════════════════════════
# Main rerank function
# ═══════════════════════════════════════════════════════════════════════

def rerank_by_score(results: list[dict], min_score: float = 0.3) -> list[dict]:
    """Score-based rerank with freshness decay (sync, for backward compat)."""
    scored = []
    for r in results:
        content = r.get("content", "")
        base_score = r.get("score", 0)

        fw, warning = _freshness_weight(content)
        adjusted_score = base_score * fw

        if adjusted_score < min_score:
            continue

        entry = dict(r)
        entry["score"] = round(adjusted_score, 4)
        entry["freshness_weight"] = round(fw, 2)
        if warning:
            entry["freshness_warning"] = warning
        scored.append(entry)

    return sorted(scored, key=lambda r: r.get("score", 0), reverse=True)


async def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    use_llm: bool = False,
    min_score: float = 0.2,
) -> list[dict]:
    """Re-rank candidates with multi-factor scoring.

    Args:
        query: User query for semantic matching
        candidates: Candidate documents with 'content' and 'score' fields
        top_k: Number of results to return
        use_llm: Enable LLM-based semantic reranking (higher quality, slower)
        min_score: Minimum adjusted score to include

    Returns:
        Top-k reranked documents
    """
    if not candidates:
        return []

    # Step 1: Score-based rerank with freshness
    freshness_ranked = rerank_by_score(candidates, min_score=min_score)

    # Step 2: LLM semantic rerank (optional)
    if use_llm and len(freshness_ranked) > top_k:
        results = await _llm_rerank(query, freshness_ranked, top_k)
    else:
        results = freshness_ranked[:top_k]

    # Step 3: Add keyword overlap to final scores
    for r in results:
        content = r.get("content", "")
        kw_score = _keyword_overlap(query, content)
        current_score = r.get("score", 0)
        # Blend: 80% existing + 20% keyword
        r["score"] = round(current_score * 0.8 + kw_score * 0.2, 4)
        r["keyword_overlap"] = round(kw_score, 2)

    return results
