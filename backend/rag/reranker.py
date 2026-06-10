"""Rerank search results with freshness decay.

v5: Added document freshness scoring. Older documents are penalized
to prevent stale data from contaminating recommendations.

Rules:
  - <= 30 days: full score
  - 30-90 days: 10% decay
  - 90-180 days: 50% decay (marked as "possibly stale")
  - > 180 days: 80% decay (marked as "likely outdated")
"""

import re
from datetime import datetime, timezone


FRESH_THRESHOLD_30 = 30
FRESH_THRESHOLD_90 = 90
FRESH_THRESHOLD_180 = 180


def _extract_date(content: str) -> datetime | None:
    """Try to extract an updated_at date from content."""
    # Look for YAML frontmatter updated_at field
    match = re.search(r'updated_at[:：]\s*(\d{4}-\d{2}-\d{2})', content)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _freshness_weight(content: str) -> tuple[float, str | None]:
    """Compute freshness weight multiplier and optional warning."""
    updated = _extract_date(content)
    if updated is None:
        # No date found — assume moderate freshness
        return 0.8, None

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


def rerank_by_score(results: list[dict], min_score: float = 0.3) -> list[dict]:
    """Filter and re-rank results by relevance score, with freshness decay."""
    scored = []
    for r in results:
        content = r.get("content", "")
        base_score = r.get("score", 0)

        # Apply freshness decay
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
) -> list[dict]:
    """Re-rank candidates with freshness awareness. Returns top_k results."""
    reranked = rerank_by_score(candidates)
    return reranked[:top_k]
