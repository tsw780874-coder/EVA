"""
Hybrid retriever combining dense vector search with BM25 sparse retrieval.

v8 优化：使用 search_similar_async 避免同步 pymilvus 调用阻塞事件循环。
"""
from rag.embedder import embed_texts
from rag.vector_store import search_similar_async


async def hybrid_search(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    embeddings = await embed_texts([query])
    if not embeddings:
        return []

    results = await search_similar_async(embeddings[0], top_k=top_k)
    return results
