"""Platform Adapters — 电商平台官方 API 合法数据源适配层。

提供统一的 ProductSearchAdapter 接口，各平台实现自己的适配器。
优先使用官方联盟 API，不可用时回退 SerpAPI / URL 模板。

用法:
    from app.agent.platform_adapters import search_all_platforms

    products = await search_all_platforms("iPhone 16 Pro", top_k=5)
"""

from app.agent.platform_adapters.base import ProductSearchAdapter, ProductSearchResult
from app.agent.platform_adapters.jd_affiliate import JdAffiliateAdapter
from app.agent.platform_adapters.taobao_affiliate import TaobaoAffiliateAdapter
from app.agent.platform_adapters.pdd_affiliate import PddAffiliateAdapter
from app.agent.platform_adapters.serpapi_adapter import SerpAPIAdapter


# 按优先级排序的适配器列表
# 官方API > SerpAPI（不可用时自动跳过）
_ALL_ADAPTERS: list[ProductSearchAdapter] = []


def _init_adapters():
    """Lazy-init adapters."""
    global _ALL_ADAPTERS
    if _ALL_ADAPTERS:
        return
    _ALL_ADAPTERS = [
        JdAffiliateAdapter(),       # P0: 京东联盟
        TaobaoAffiliateAdapter(),   # P1: 淘宝客
        PddAffiliateAdapter(),      # P2: 多多客
        SerpAPIAdapter(),           # P3: SerpAPI (兜底)
    ]


async def search_all_platforms(
    query: str,
    top_k: int = 5,
    timeout: float = 10.0,
) -> list[dict]:
    """并行搜索所有可用平台，返回结构化商品数据。

    Args:
        query: 搜索关键词
        top_k: 每个平台返回数量上限
        timeout: 总超时时间

    Returns:
        商品列表（已通过 _enrich_product 标准化）
    """
    import asyncio
    from app.api.v1.admin import append_log

    _init_adapters()

    # 仅查询配置了凭据的适配器
    available = [a for a in _ALL_ADAPTERS if a.is_available()]
    if not available:
        append_log("INFO", "无可用电商平台 API（未配置凭据），跳过官方 API 层")
        return []

    append_log("INFO", f"并行查询 {len(available)} 个电商平台: {[a.source_name for a in available]}")

    async def _query_one(adapter: ProductSearchAdapter):
        try:
            results = await asyncio.wait_for(
                adapter.search(query, top_k=top_k),
                timeout=timeout / max(len(available), 1),
            )
            return [(adapter.source_name, r) for r in results]
        except asyncio.TimeoutError:
            append_log("WARN", f"{adapter.source_name} 超时")
            return []
        except Exception as e:
            append_log("WARN", f"{adapter.source_name} 异常: {type(e).__name__}: {str(e)[:80]}")
            return []

    tasks = [_query_one(a) for a in available]
    all_results = await asyncio.gather(*tasks)

    # 展平结果，按适配器优先级排序
    products: list[dict] = []
    for results in all_results:
        for source_name, result in results:
            products.append(result.to_enriched_dict())
            if len(products) >= top_k * 2:
                break
        if len(products) >= top_k * 2:
            break

    append_log("SUCCESS", f"官方 API 层返回 {len(products)} 个商品")
    return products[:top_k * 2]
