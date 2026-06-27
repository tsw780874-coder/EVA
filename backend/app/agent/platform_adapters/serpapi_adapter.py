"""SerpAPI Google Shopping 适配器 — 包装现有 serpapi 搜索为统一接口。

作为官方 API 的兜底方案，优先级低于京东/淘宝/拼多多联盟 API。
"""

from app.agent.platform_adapters.base import ProductSearchAdapter, ProductSearchResult
from app.config import get_settings


class SerpAPIAdapter(ProductSearchAdapter):
    """SerpAPI Google Shopping 适配器。

    包装现有的 serpapi_search.py 为 ProductSearchAdapter 接口。
    """

    def __init__(self):
        settings = get_settings()
        self.api_key: str = getattr(settings, "serpapi_key", "") or ""

    @property
    def source_name(self) -> str:
        return "serpapi_shopping"

    @property
    def priority(self) -> int:
        return 40  # 低于官方 API

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        top_k: int = 5,
        timeout: float = 10.0,
    ) -> list[ProductSearchResult]:
        if not self.is_available():
            return []

        try:
            from app.agent.serpapi_search import serpapi_product_search
            raw_results = await serpapi_product_search(query, top_k=top_k, timeout=timeout)

            results: list[ProductSearchResult] = []
            for p in raw_results:
                results.append(ProductSearchResult(
                    name=p.get("name", ""),
                    price=float(p.get("price", 0)) if p.get("price") else 0,
                    original_price=float(p.get("original_price", 0)) if p.get("original_price") else 0.0,
                    platform=p.get("platform", "未知"),
                    url=p.get("url", ""),
                    image_url=p.get("image_url", ""),
                    rating=float(p.get("rating", 0)) if p.get("rating") else None,
                    review_count=int(p.get("review_count", 0)) if p.get("review_count") else 0,
                    source=self.source_name,
                    confidence=float(p.get("confidence", 70.0)),
                    raw_data=p,
                ))

            return results

        except ImportError:
            return []
        except Exception:
            return []
