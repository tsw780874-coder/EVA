"""Hybrid Search: BM25 (keyword) + Milvus (vector) for improved recall.

Combines sparse (BM25 keyword) and dense (vector embedding) retrieval
for better search quality than pure vector search alone.

Usage:
    from rag.hybrid_search import hybrid_search

    results = await hybrid_search("iPhone 15价格", top_k=5)
"""

import hashlib
from rag.retriever import hybrid_search as _vector_search
from app.api.v1.admin import append_log


# ── Simple BM25 implementation (no external deps) ──

class SimpleBM25:
    """Minimal BM25 scorer using TF term frequency.

    For production, replace with rank_bm25 or Elasticsearch.
    """

    def __init__(self, documents: list[dict]):
        self.docs = documents
        self._doc_texts = [d.get("content", "") for d in documents]
        self._avg_dl = sum(len(t) for t in self._doc_texts) / max(len(self._doc_texts), 1)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        """Score documents against query using simplified BM25."""
        query_terms = query.lower().split()
        if not query_terms:
            return self.docs[:top_k]

        k1 = 1.5
        b = 0.75

        scored = []
        for i, doc in enumerate(self.docs):
            text = self._doc_texts[i].lower()
            dl = len(text)
            score = 0.0

            for term in query_terms:
                tf = text.count(term)
                if tf == 0:
                    continue
                # Simplified BM25 TF component
                tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(self._avg_dl, 1)))
                score += tf_norm

            if score > 0:
                doc_copy = dict(doc)
                doc_copy["bm25_score"] = score
                scored.append(doc_copy)

        scored.sort(key=lambda d: d.get("bm25_score", 0), reverse=True)
        return scored[:top_k]


# ── BM25 document store ──
_bm25_index: SimpleBM25 | None = None
_bm25_docs_hash: str = ""


def _update_bm25_index(documents: list[dict]):
    """Update the BM25 index with new documents."""
    global _bm25_index, _bm25_docs_hash
    doc_hash = hashlib.md5(
        "".join(d.get("content", "")[:100] for d in documents).encode()
    ).hexdigest()

    if _bm25_index is None or doc_hash != _bm25_docs_hash:
        _bm25_index = SimpleBM25(documents)
        _bm25_docs_hash = doc_hash


def _merge_results(
    vector_results: list[dict],
    bm25_results: list[dict],
    top_k: int,
    vector_weight: float = 0.6,
) -> list[dict]:
    """Merge and deduplicate vector + BM25 results."""
    combined: dict[str, dict] = {}
    content_hash = lambda c: hashlib.md5(c[:100].encode()).hexdigest()

    # Vector results (weighted)
    for r in vector_results:
        h = content_hash(r.get("content", ""))
        score = r.get("score", 0.0)
        combined[h] = {
            **r,
            "score": score * vector_weight,
            "match_type": "vector",
        }

    # BM25 results (weighted, normalized)
    max_bm25 = max((r.get("bm25_score", 0) for r in bm25_results), default=1.0)
    for r in bm25_results:
        h = content_hash(r.get("content", ""))
        norm_score = (r.get("bm25_score", 0) / max(max_bm25, 1.0)) * (1 - vector_weight)
        if h in combined:
            combined[h]["score"] += norm_score
            combined[h]["match_type"] = "hybrid"
        else:
            combined[h] = {
                **r,
                "score": norm_score,
                "match_type": "bm25",
            }

    # Sort and return top_k
    sorted_results = sorted(combined.values(), key=lambda r: r.get("score", 0), reverse=True)
    return sorted_results[:top_k]


# ── Public API ──

async def hybrid_search(
    query: str,
    top_k: int = 5,
    candidates: list[dict] | None = None,
) -> list[dict]:
    """Hybrid search combining BM25 keyword + Milvus vector retrieval.

    Args:
        query: Search query text
        top_k: Number of results to return
        candidates: Optional pre-fetched candidate pool (from RAG)

    Returns:
        List of deduplicated, merged results with scores.
    """
    # Vector search
    vector_results = await _vector_search(query, top_k=top_k)

    # BM25 search on the same candidate pool
    if candidates:
        _update_bm25_index(candidates)
        bm25_results = _bm25_index.search(query, top_k=top_k) if _bm25_index else []
    elif vector_results:
        _update_bm25_index(vector_results)
        bm25_results = _bm25_index.search(query, top_k=top_k) if _bm25_index else []
    else:
        bm25_results = []

    merged = _merge_results(vector_results, bm25_results, top_k)

    hybrid_count = sum(1 for r in merged if r.get("match_type") == "hybrid")
    append_log(
        "DEBUG",
        f"hybrid_search: vector={len(vector_results)} bm25={len(bm25_results)} "
        f"merged={len(merged)} hybrid_matches={hybrid_count}",
    )

    return merged
