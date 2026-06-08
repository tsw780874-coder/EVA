"""
RAG service: document ingestion, search, and management.
"""
from rag.loader import load_directory
from rag.chunker import chunk_documents
from rag.embedder import embed_documents
from rag.vector_store import insert_documents, search_similar
from rag.retriever import hybrid_search
from rag.reranker import rerank


async def ingest_directory(directory: str) -> int:
    """Ingest all documents from a directory into the vector store."""
    docs = load_directory(directory)
    if not docs:
        return 0

    chunks = chunk_documents(docs)
    if not chunks:
        return 0

    await embed_documents(chunks)
    insert_documents(chunks)
    return len(chunks)


async def search_knowledge(query: str, top_k: int = 5) -> list[dict]:
    """Search the knowledge base with hybrid retrieval and reranking."""
    candidates = await hybrid_search(query, top_k=top_k * 2)
    return await rerank(query, candidates, top_k=top_k)
