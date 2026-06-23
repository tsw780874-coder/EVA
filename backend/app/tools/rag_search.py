"""RAG Search Tool — 知识库语义搜索

数据源: Milvus 向量数据库 + BM25 关键词搜索
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="rag_search",
    description="在知识库中搜索相关内容。支持产品评价、购买指南、技术参数、FAQ等。适用于需要详细背景知识的问题。",
    category="search",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询文本",
            },
            "top_k": {
                "type": "integer",
                "description": "返回文档数量，默认5",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def search_rag(query: str, top_k: int = 5) -> ToolResult:
    """RAG知识库搜索"""
    try:
        from app.services.rag_service import search_knowledge

        docs = await search_knowledge(query, top_k=top_k)

        if not docs:
            return ToolResult.partial(
                tool="rag_search",
                data=[],
                confidence=0.0,
                source="rag_knowledge_base",
                error="知识库中未找到相关内容",
            )

        # 格式化为结构化数据
        results = []
        for doc in docs:
            results.append({
                "content": doc.get("content", "")[:500],
                "score": doc.get("score", 0.0),
                "source_file": doc.get("source", "unknown"),
                "metadata": doc.get("metadata", {}),
            })

        avg_score = sum(d.get("score", 0) for d in results) / len(results)
        confidence = min(avg_score, 0.9)

        return ToolResult.success(
            tool="rag_search",
            data=results,
            confidence=confidence,
            source="rag_knowledge_base",
            total_docs=len(results),
        )

    except Exception as e:
        return ToolResult.failed(
            tool="rag_search",
            error=f"RAG搜索失败: {str(e)[:200]}",
        )
