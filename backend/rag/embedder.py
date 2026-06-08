"""
Generate embeddings for document chunks using OpenAI API.
Can be swapped for local models (BGE-M3, etc.) in production.
"""
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()


async def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    model = model or "text-embedding-3-small"

    resp = await client.embeddings.create(model=model, input=texts)
    return [e.embedding for e in resp.data]


async def embed_documents(documents: list[dict]) -> list[dict]:
    """Embed all documents in a batch."""
    texts = [doc["content"] for doc in documents]
    embeddings = await embed_texts(texts)

    for doc, emb in zip(documents, embeddings):
        doc["embedding"] = emb

    return documents
