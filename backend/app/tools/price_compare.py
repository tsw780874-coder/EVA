"""Price Compare Tool — 多平台价格对比

数据源: 实时电商搜索 + Web搜索
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="price_compare",
    description="对比同一商品在多个平台（京东、天猫、淘宝、得物、拼多多等）的价格。返回各平台价格列表和最低价推荐。",
    category="search",
    parameters={
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "商品名称（需包含品牌和型号）",
            },
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "指定平台列表，如 ['京东', '天猫', '得物']，默认全部",
            },
        },
        "required": ["product_name"],
    },
)
async def compare_price(
    product_name: str,
    platforms: list[str] | None = None,
) -> ToolResult:
    """多平台价格对比"""
    try:
        from app.agent.live_search import live_search_products

        products = await live_search_products(
            query=product_name,
            top_k=10,
            user_id="tool",
            timeout=5.0,
        )

        if platforms:
            products = [
                p for p in products
                if p.get("platform", "") in platforms
            ]

        if not products:
            # 回退：尝试生成搜索链接
            from app.agent.live_search import generate_search_urls
            urls = generate_search_urls(product_name)
            url_data = [
                {"platform": k, "search_url": v, "price": None}
                for k, v in urls.items()
            ]
            return ToolResult.partial(
                tool="price_compare",
                data=url_data,
                confidence=0.15,
                source="url_generation",
                error="实时价格获取失败，返回搜索链接",
            )

        # 按价格排序
        products.sort(key=lambda p: p.get("price", float("inf")))

        # 标注最低价
        if products:
            products[0]["is_lowest"] = True

        real_count = sum(1 for p in products if p.get("source") != "simulated")
        confidence = min(real_count / max(len(products), 1), 0.9)

        return ToolResult.success(
            tool="price_compare",
            data=products,
            confidence=confidence,
            source="live_search",
            platform_count=len(set(p.get("platform", "?") for p in products)),
            lowest_price=products[0].get("price") if products else None,
        )

    except Exception as e:
        return ToolResult.failed(
            tool="price_compare",
            error=f"价格对比失败: {str(e)[:200]}",
        )
