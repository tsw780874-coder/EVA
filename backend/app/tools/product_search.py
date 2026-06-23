"""Product Search Tool — 统一商品搜索

数据源: RAG知识库 + 商品缓存 + 热门商品 + 实时电商搜索
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="product_search",
    description="搜索商品信息，支持按名称、品牌、型号、类别搜索。返回商品列表（价格、平台、评分、链接）。",
    category="search",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，如商品名称、品牌、型号",
            },
            "top_k": {
                "type": "integer",
                "description": "返回商品数量上限，默认5",
                "default": 5,
            },
            "category": {
                "type": "string",
                "description": "商品类别过滤（可选）",
            },
            "min_price": {
                "type": "number",
                "description": "最低价格过滤（可选）",
            },
            "max_price": {
                "type": "number",
                "description": "最高价格过滤（可选）",
            },
        },
        "required": ["query"],
    },
)
async def search_products(
    query: str,
    top_k: int = 5,
    category: str = "",
    min_price: float = 0,
    max_price: float = 0,
) -> ToolResult:
    """搜索商品 — 聚合多个数据源"""
    try:
        from app.agent.pipeline import run_pipeline

        result = await run_pipeline(
            user_query=query,
            user_id="tool",
            bypass_cache=False,
        )

        products = result.get("search_results", [])
        search_layers = result.get("search_layers", [])

        # 类别过滤
        if category and products:
            products = [
                p for p in products
                if category.lower() in (
                    (p.get("category") or "").lower()
                )
            ]

        # 价格过滤
        if min_price > 0:
            products = [p for p in products if p.get("price", 0) >= min_price]
        if max_price > 0:
            products = [p for p in products if p.get("price", 0) <= max_price]

        # 截取 top_k
        products = products[:top_k]

        # 计算置信度
        real_count = sum(1 for p in products if p.get("source") != "simulated")
        confidence = real_count / max(len(products), 1) if products else 0.0

        search_layer_map = {
            "hot_products": "热门商品库",
            "trending_normalize": "趋势关键词匹配",
            "rag": "RAG知识库",
            "product_cache": "商品缓存库",
            "live_search": "电商实时搜索",
            "similar_search": "相似商品匹配",
            "template": "模板匹配",
            "link_fallback": "链接回退",
        }
        source = ", ".join(
            search_layer_map.get(l, l) for l in search_layers[:3]
        ) or "unknown"

        if not products:
            return ToolResult.partial(
                tool="product_search",
                data=[],
                confidence=0.0,
                source=source,
                error=f"未找到与 '{query}' 相关的商品",
                search_layers=search_layers,
            )

        return ToolResult.success(
            tool="product_search",
            data=products,
            confidence=min(confidence, 0.95),
            source=source,
            total_found=len(products),
            search_layers=search_layers,
            data_source=result.get("data_source", "unknown"),
        )

    except Exception as e:
        return ToolResult.failed(
            tool="product_search",
            error=f"商品搜索失败: {str(e)[:200]}",
        )
