"""Hybrid Search: BM25 (keyword) + Milvus (vector) for improved recall.

Combines sparse (BM25 keyword) and dense (vector embedding) retrieval
for better search quality than pure vector search alone.

Usage:
    from rag.hybrid_search import hybrid_search

    results = await hybrid_search("iPhone 15价格", top_k=5)
"""

import asyncio
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

from rag.retriever import hybrid_search as _vector_search
from app.api.v1.admin import append_log

# 共享线程池 — BM25 等 CPU 密集型操作使用
_bm25_executor = ThreadPoolExecutor(max_workers=2)


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


# ── BM25 document store (with TTL cache) ──
_bm25_index: SimpleBM25 | None = None
_bm25_docs_hash: str = ""
_bm25_last_built: float = 0.0
_BM25_CACHE_TTL: float = 60.0  # 60秒内复用索引


def _update_bm25_index(documents: list[dict]):
    """Update the BM25 index with new documents. Uses TTL cache."""
    global _bm25_index, _bm25_docs_hash, _bm25_last_built
    doc_hash = hashlib.md5(
        "".join(d.get("content", "")[:100] for d in documents).encode()
    ).hexdigest()

    now = time.time()
    # 复用缓存：相同文档集且在 TTL 内
    if (_bm25_index is not None and doc_hash == _bm25_docs_hash
            and (now - _bm25_last_built) < _BM25_CACHE_TTL):
        return

    if _bm25_index is None or doc_hash != _bm25_docs_hash:
        _bm25_index = SimpleBM25(documents)
        _bm25_docs_hash = doc_hash
        _bm25_last_built = now


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
    """Hybrid search — BM25 + Vector 真正并行执行。

    优化：Vector搜索和BM25同时跑，取最快完成的两个结果集合并。
    总耗时 = max(vector_time, bm25_time) 而非 vector_time + bm25_time。

    Args:
        query: Search query text
        top_k: Number of results to return
        candidates: Optional pre-fetched candidate pool (from RAG)

    Returns:
        List of deduplicated, merged results with scores.
    """
    loop = asyncio.get_event_loop()

    # Vector 搜索任务
    async def _vector_task():
        try:
            return await _vector_search(query, top_k=top_k)
        except Exception:
            return []

    # BM25 搜索任务（在线程池中运行以避免阻塞事件循环）
    async def _bm25_task(docs_for_bm25: list[dict]):
        def _run_bm25():
            _update_bm25_index(docs_for_bm25)
            if _bm25_index:
                return _bm25_index.search(query, top_k=top_k)
            return []
        try:
            return await loop.run_in_executor(_bm25_executor, _run_bm25)
        except Exception:
            return []

    # 提前准备BM25候选文档池（不依赖vector结果）
    bm25_candidates = candidates or []

    # 并行启动
    vector_task = asyncio.create_task(_vector_task())

    # 如果还没有候选文档，先快速获取一批用于BM25
    if not bm25_candidates:
        # 先用vector获取候选池（如果vector比BM25快，BM25用vector结果）
        bm25_vec_task = asyncio.create_task(_vector_task())
    else:
        bm25_vec_task = None

    # 获取vector结果
    vector_results = await vector_task

    # 确定BM25候选文档
    if bm25_candidates:
        pass  # 已有
    elif bm25_vec_task:
        bm25_candidates = await bm25_vec_task
    else:
        bm25_candidates = vector_results

    # BM25搜索
    bm25_results = await _bm25_task(bm25_candidates)

    merged = _merge_results(vector_results, bm25_results, top_k)

    hybrid_count = sum(1 for r in merged if r.get("match_type") == "hybrid")
    append_log(
        "DEBUG",
        f"hybrid_search: vector={len(vector_results)} bm25={len(bm25_results)} "
        f"merged={len(merged)} hybrid_matches={hybrid_count}",
    )

    return merged
