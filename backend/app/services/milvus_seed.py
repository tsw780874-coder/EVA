"""Milvus Knowledge Base Seeding — 将商品百科数据导入 Milvus 向量库.

Usage:
    # CLI 手动执行
    python -m app.services.milvus_seed

    # 代码调用
    from app.services.milvus_seed import seed_knowledge_base
    await seed_knowledge_base()

    # 启动时自动检测空集合并导入
    from app.services.milvus_seed import auto_seed_on_startup
    await auto_seed_on_startup()
"""

import asyncio
import logging
import time
from typing import Optional

from app.api.v1.admin import append_log

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# 数据源：商品百科 → 文档 → 分块 → 向量化 → Milvus
# ═══════════════════════════════════════════════════════════════════════

async def _load_wiki_documents() -> list[dict]:
    """从 product_wiki 加载所有商品百科条目，转换为 RAG 文档格式."""
    try:
        from app.agent.product_wiki import get_all_wiki_entries
    except ImportError:
        append_log("WARN", "product_wiki 模块不可用，跳过 Wiki 数据加载")
        return []

    entries = get_all_wiki_entries()
    docs: list[dict] = []

    for entry in entries:
        # 构建结构化文档内容（YAML frontmatter + Markdown body）
        content_parts = [
            "---",
            f"name: {entry.get('name', '')}",
            f"brand: {entry.get('brand', '')}",
            f"model: {entry.get('model', '')}",
            f"category: {entry.get('category', '')}",
            f"subcategory: {entry.get('subcategory', '')}",
            f"source: product_wiki",
            "platforms:",
        ]

        # 追加平台价格列表
        platforms = entry.get("platforms", [])
        for plat in platforms:
            content_parts.append(f"  - name: {plat.get('name', '')}")
            content_parts.append(f"    price: {plat.get('price', '')}")
            content_parts.append(f"    url: {plat.get('url', '')}")

        content_parts.append(f"rating: {entry.get('rating', '')}")
        content_parts.append(f"review_count: {entry.get('review_count', '')}")
        content_parts.append(f"popularity_score: {entry.get('popularity_score', 50)}")
        content_parts.append("---")
        content_parts.append("")

        # 追加正文（描述 / 评测 / 购买建议）
        body = entry.get("content", "") or entry.get("description", "")
        if not body:
            # 从结构数据生成描述
            name = entry.get("name", "")
            brand = entry.get("brand", "")
            category = entry.get("category", "")
            price_ranges = []
            for plat in platforms:
                pname = plat.get("name", "")
                pprice = plat.get("price", "")
                if pname and pprice:
                    price_ranges.append(f"{pname}: ¥{pprice}")
            body = f"{name}（{brand}，{category}）\n" + "\n".join(price_ranges)

        content_parts.append(body)
        content = "\n".join(content_parts)

        docs.append({
            "content": content,
            "metadata": {
                "source": "product_wiki",
                "source_name": entry.get("name", ""),
                "brand": entry.get("brand", ""),
                "category": entry.get("category", ""),
            },
        })

    return docs


async def _chunk_and_embed(docs: list[dict]) -> list[dict]:
    """将文档分块 + 向量化."""
    if not docs:
        return []

    try:
        from rag.chunker import chunk_documents
        from rag.embedder import embed_documents
    except ImportError as e:
        append_log("WARN", f"RAG 模块不可用，跳过分块/向量化: {e}")
        return []

    # 分块
    t0 = time.perf_counter()
    chunks = chunk_documents(docs, chunk_size=512, chunk_overlap=50)
    append_log("INFO", f"Milvus 种子: {len(docs)} 文档 → {len(chunks)} 块")

    # 向量化（批量调用 OpenAI embedding API）
    try:
        chunk_dicts = await embed_documents(chunks)
    except Exception as e:
        append_log("ERROR", f"向量化失败（OpenAI API 可能不可用）: {e}")
        return []

    elapsed = (time.perf_counter() - t0) * 1000
    append_log("INFO", f"向量化完成: {len(chunk_dicts)} 块, {elapsed:.0f}ms")
    return chunk_dicts


async def _insert_to_milvus(chunks: list[dict]) -> int:
    """将向量块插入 Milvus eva_knowledge 集合."""
    if not chunks:
        return 0

    try:
        from rag.vector_store import insert_documents_async
    except ImportError:
        append_log("WARN", "vector_store 模块不可用")
        return 0

    try:
        inserted = await insert_documents_async(chunks)
        append_log("INFO", f"Milvus 种子完成: {inserted} 条记录写入 eva_knowledge")
        return inserted
    except Exception as e:
        append_log("ERROR", f"Milvus 写入失败: {e}")
        return 0


async def seed_knowledge_base(force: bool = False) -> int:
    """将商品百科数据导入 Milvus 知识库.

    Args:
        force: 是否强制重新导入（即使集合已有数据）

    Returns:
        导入的记录数
    """
    append_log("INFO", "Milvus 知识库种子开始...")

    # 检查集合是否已有数据
    if not force:
        try:
            from rag.vector_store import search_similar_async
            check = await search_similar_async([0.0] * 1536, top_k=1, timeout=1.0)
            if check and len(check) > 0:
                append_log("INFO", f"Milvus eva_knowledge 已有 {len(check)}+ 条记录，跳过种子")
                return 0
        except Exception:
            pass  # 集合可能不存在，继续创建

    # 加载 → 分块 → 向量化 → 写入
    docs = await _load_wiki_documents()
    if not docs:
        append_log("WARN", "无 Wiki 数据可导入")
        return 0

    chunks = await _chunk_and_embed(docs)
    if not chunks:
        return 0

    count = await _insert_to_milvus(chunks)
    return count


async def auto_seed_on_startup():
    """FastAPI 启动时自动检测并填充 Milvus（仅当集合为空时）.

    放在 FastAPI lifespan startup 事件中调用。
    失败不影响服务启动。
    """
    try:
        await asyncio.wait_for(seed_knowledge_base(force=False), timeout=180.0)
    except asyncio.TimeoutError:
        append_log("WARN", "Milvus 自动种子超时（>180s），跳过")
    except Exception as e:
        append_log("WARN", f"Milvus 自动种子失败: {str(e)[:80]}")


# ═══════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Milvus 知识库种子工具")
    print("=" * 40)
    asyncio.run(seed_knowledge_base(force=True))
    print("完成。")
