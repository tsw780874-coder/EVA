"""Vector Memory Service — Milvus 向量记忆 (L3 Retrieval Memory)

将 MySQL 中的结构化记忆向量化存储到 Milvus:
  - 用户偏好 → embed → Milvus eva_memory collection
  - 已确认事实 → embed → Milvus
  - 聊天摘要 → embed → Milvus
  - FAQ → embed → Milvus

仅存储验证通过的可信数据。
"""

import json
import time
from datetime import datetime, timezone


async def store_vector_memories(
    user_id: str,
    facts: list[dict],
    collection_name: str = "eva_memory",
) -> int:
    """将可信事实向量化并存入 Milvus。

    Args:
        user_id: 用户ID
        facts: 事实列表，每条包含 key, value, importance, memory_type, source
        collection_name: Milvus collection 名称

    Returns:
        成功写入的向量数量
    """
    try:
        from app.rag.embedder import get_embedder
        from app.rag.vector_store import get_vector_store

        embedder = get_embedder()
        store = get_vector_store(collection_name)

        stored = 0
        for fact in facts:
            # 构建嵌入文本
            fact_type = fact.get("memory_type", "general")
            fact_key = fact.get("key", "")
            fact_value = fact.get("value", {})
            if isinstance(fact_value, dict):
                fact_text = fact_value.get("preference") or fact_value.get("confirmed_choice") or json.dumps(fact_value, ensure_ascii=False)
            else:
                fact_text = str(fact_value)

            embed_text = f"[{fact_type}] {fact_key}: {fact_text[:500]}"

            try:
                # 生成 embedding
                embedding = await embedder.embed_texts([embed_text])

                # 写入 Milvus
                await store.insert(
                    texts=[embed_text],
                    embeddings=embedding,
                    metadatas=[{
                        "user_id": user_id,
                        "memory_type": fact_type,
                        "importance": fact.get("importance", 0.5),
                        "source": fact.get("source", "unknown"),
                        "stored_at": datetime.now(timezone.utc).isoformat(),
                    }],
                )
                stored += 1
            except Exception:
                continue  # 单条失败不阻塞其他

        return stored

    except ImportError:
        return 0  # Milvus 不可用（slim/light 部署）
    except Exception:
        return 0


async def search_vector_memories(
    user_id: str,
    query: str,
    top_k: int = 5,
    memory_type: str | None = None,
) -> list[dict]:
    """语义搜索向量记忆。

    Args:
        user_id: 用户ID
        query: 搜索查询
        top_k: 返回数量
        memory_type: 记忆类型过滤（可选）

    Returns:
        匹配的记忆列表
    """
    try:
        from app.rag.embedder import get_embedder
        from app.rag.vector_store import get_vector_store

        embedder = get_embedder()
        store = get_vector_store("eva_memory")

        # 生成查询向量
        query_embedding = await embedder.embed_texts([query])

        # 构建过滤表达式
        filter_expr = f'user_id == "{user_id}"'
        if memory_type:
            filter_expr += f' && memory_type == "{memory_type}"'

        # 向量搜索
        results = await store.search(
            query_embeddings=query_embedding,
            top_k=top_k,
            filter_expr=filter_expr,
        )

        memories = []
        for res in results:
            memories.append({
                "text": res.get("text", ""),
                "score": res.get("score", 0.0),
                "memory_type": res.get("metadata", {}).get("memory_type", ""),
                "importance": res.get("metadata", {}).get("importance", 0.0),
                "source": res.get("metadata", {}).get("source", ""),
            })

        return memories

    except ImportError:
        return []  # Milvus 不可用
    except Exception:
        return []


async def delete_user_vector_memories(user_id: str) -> int:
    """删除用户的所有向量记忆"""
    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store("eva_memory")
        deleted = await store.delete(filter_expr=f'user_id == "{user_id}"')
        return deleted
    except Exception:
        return 0


async def get_memory_stats(user_id: str) -> dict:
    """获取用户记忆统计"""
    try:
        from app.rag.vector_store import get_vector_store
        store = get_vector_store("eva_memory")
        # 尝试获取 collection 信息
        stats = {
            "has_vector_memory": True,
            "user_id": user_id,
        }
        return stats
    except Exception:
        return {"has_vector_memory": False, "user_id": user_id}
