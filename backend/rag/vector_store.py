"""
Milvus vector store wrapper for document storage and retrieval.

v8 优化：同步 pymilvus 调用通过 run_in_executor 包装到线程池，
避免阻塞 asyncio 事件循环。
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from pymilvus import (
    connections, Collection, CollectionSchema,
    FieldSchema, DataType, utility,
)
from app.config import get_settings

settings = get_settings()
COLLECTION_NAME = "eva_knowledge"
DIM = 1536  # text-embedding-3-small dimension

# 共享线程池 — Milvus 同步调用在此执行
_milvus_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="milvus")


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


async def insert_documents_async(documents: list[dict]):
    """异步插入文档 — 在线程池中运行同步 pymilvus 调用。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_milvus_executor, insert_documents, documents)


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


async def search_similar_async(
    query_embedding: list[float],
    top_k: int = 5,
    timeout: float = 2.0,
) -> list[dict]:
    """异步向量搜索 — 在线程池中运行同步 pymilvus 调用，带超时。

    解决核心问题：pymilvus collection.search() 是同步调用，
    在主事件循环中直接调用会阻塞所有其他协程。
    """
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _milvus_executor,
                search_similar,
                query_embedding,
                top_k,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        from app.api.v1.admin import append_log
        append_log("WARN", f"Milvus 搜索超时 ({timeout}s)")
        return []
