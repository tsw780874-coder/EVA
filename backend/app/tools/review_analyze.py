"""Review Analysis Tool — 商品评价分析

数据源: RAG知识库中的评价数据
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="review_analyze",
    description="分析商品的用户评价和口碑。返回好评率、关键评价摘要、优缺点分析。适用于了解商品真实使用体验。",
    category="data",
    parameters={
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "商品名称（品牌+型号）",
            },
        },
        "required": ["product_name"],
    },
)
async def analyze_reviews(product_name: str) -> ToolResult:
    """商品评价分析"""
    try:
        from app.services.rag_service import search_knowledge

        # 在知识库中搜索评价相关内容
        docs = await search_knowledge(
            f"{product_name} 评价 口碑 用户体验",
            top_k=8,
        )

        if not docs:
            return ToolResult.partial(
                tool="review_analyze",
                data=[],
                confidence=0.1,
                source="rag_knowledge_base",
                error=f"未找到 '{product_name}' 的评价数据",
            )

        # 尝试用 LLM 分析评价
        try:
            from app.agent.llm_utils import llm_call

            review_text = "\n".join(
                f"[评价{i+1}] {doc.get('content', '')[:300]}"
                for i, doc in enumerate(docs[:5])
            )

            analysis, _, _ = await llm_call(
                system_prompt=(
                    "你是电商评价分析专家。基于提供的用户评价，提取以下信息：\n"
                    "1. 整体好评率（估计百分比）\n"
                    "2. 主要优点（3-5条）\n"
                    "3. 主要缺点（2-3条）\n"
                    "4. 适合人群\n"
                    "5. 综合评分（1-5星）\n"
                    "只使用提供的评价内容，不要编造。用中文回复。"
                ),
                user_message=f"商品: {product_name}\n\n评价内容:\n{review_text}",
                max_tokens=300,
                temperature=0.3,
                user_id="tool",
                node_name="review_analyze",
            )
        except Exception:
            analysis = "\n".join(
                f"- {doc.get('content', '')[:150]}"
                for doc in docs[:3]
            )

        return ToolResult.success(
            tool="review_analyze",
            data=[{
                "product": product_name,
                "analysis": analysis,
                "source_count": len(docs),
            }],
            confidence=min(0.6 + len(docs) * 0.05, 0.9),
            source="rag_knowledge_base",
            total_reviews_analyzed=len(docs),
        )

    except Exception as e:
        return ToolResult.failed(
            tool="review_analyze",
            error=f"评价分析失败: {str(e)[:200]}",
        )
