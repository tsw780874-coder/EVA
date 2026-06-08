"""
Milvus vector store wrapper for document storage and retrieval.
"""
from typing import Any
from pymilvus import (
    connections, Collection, CollectionSchema,
    FieldSchema, DataType, utility,
)
from app.config import get_settings

settings = get_settings()
COLLECTION_NAME = "eva_knowledge"
DIM = 1536  # text-embedding-3-small dimension


def _connect():
    try:
        if not connections.has_connection("default"):
            connections.connect(
                alias="default",
                host=settings.milvus_host,
                port=settings.milvus_port,
            )
    except Exception:
        pass


def create_collection():
    _connect()

    if utility.has_collection(COLLECTION_NAME):
        return Collection(COLLECTION_NAME)

    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=DIM),
    ]
    schema = CollectionSchema(fields, description="EVA Knowledge Base")
    collection = Collection(COLLECTION_NAME, schema)

    index_params = {
        "metric_type": "IP",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128},
    }
    collection.create_index("embedding", index_params)
    return collection


def insert_documents(documents: list[dict]):
    _connect()
    collection = create_collection()

    entities = [
        [doc.get("content", "") for doc in documents],
        [doc.get("metadata", {}).get("source", "") for doc in documents],
        [doc.get("embedding", []) for doc in documents],
    ]

    collection.insert(entities)
    collection.flush()


def search_similar(
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    _connect()

    if not utility.has_collection(COLLECTION_NAME):
        return []

    collection = Collection(COLLECTION_NAME)
    collection.load()

    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",
        param={"metric_type": "IP", "params": {"nprobe": 10}},
        limit=top_k,
        output_fields=["content", "source"],
    )

    return [
        {
            "content": hit.entity.get("content", ""),
            "source": hit.entity.get("source", ""),
            "score": hit.distance,
        }
        for hit in results[0]
    ]
