"""
Rerank search results using a cross-encoder approach.
For production, use a dedicated reranker model (e.g., bge-reranker-v2).
This implementation uses a simple score-based re-ranking.
"""


def rerank_by_score(results: list[dict], min_score: float = 0.3) -> list[dict]:
    """Filter and re-rank results by relevance score."""
    filtered = [r for r in results if r.get("score", 0) >= min_score]
    return sorted(filtered, key=lambda r: r.get("score", 0), reverse=True)


async def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
) -> list[dict]:
    """Re-rank candidates based on relevance to query."""
    reranked = rerank_by_score(candidates)
    return reranked[:top_k]
