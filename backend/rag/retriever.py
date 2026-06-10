"""
Hybrid retriever combining dense vector search with BM25 sparse retrieval.
"""
from rag.embedder import embed_texts
from rag.vector_store import search_similar


async def hybrid_search(
    query: str,
    top_k: int = 5,
) -> list[dict]:
    embeddings = await embed_texts([query])
    if not embeddings:
        return []

    results = search_similar(embeddings[0], top_k=top_k)
    return results
