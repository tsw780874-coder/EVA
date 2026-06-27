"""Platform Adapter Base — 所有电商平台适配器的抽象基类。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ProductSearchResult:
    """统一商品结果 — 所有适配器输出此格式。"""

    name: str
    price: float
    original_price: float = 0.0
    platform: str = ""
    url: str = ""
    image_url: str = ""
    rating: Optional[float] = None
    review_count: int = 0
    shipping_info: str = ""
    in_stock: bool = True
    brand: str = ""
    model: str = ""
    source: str = ""       # e.g. "jd_affiliate", "taobao_affiliate", "serpapi_shopping"
    confidence: float = 50.0
    raw_data: dict | None = None  # 原始 API 响应，用于调试

    def to_enriched_dict(self) -> dict:
        """转换为 pipeline 兼容的 dict 格式（用于 _enrich_product）。"""
        d = {
            "name": self.name,
            "price": self.price,
            "original_price": self.original_price if self.original_price > 0 else None,
            "platform": self.platform,
            "url": self.url,
            "image_url": self.image_url,
            "source": self.source,
            "confidence": self.confidence,
        }
        if self.rating is not None:
            d["rating"] = self.rating
        if self.review_count > 0:
            d["review_count"] = self.review_count
        if self.brand:
            d["brand"] = self.brand
        if self.model:
            d["model"] = self.model
        return d


class ProductSearchAdapter(ABC):
    """电商平台搜索适配器抽象基类。

    每个平台实现此接口，提供统一的产品搜索能力。
    适配器可以组合多个底层数据源（API + fallback）。
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 5,
        timeout: float = 10.0,
    ) -> list[ProductSearchResult]:
        """搜索商品并返回结构化结果。

        Args:
            query: 搜索关键词
            top_k: 最大返回数量
            timeout: 超时时间（秒）

        Returns:
            ProductSearchResult 列表（可为空）
        """

    @abstractmethod
    def is_available(self) -> bool:
        """检查适配器凭据是否已配置且可用。"""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """唯一的数据源标识符。"""

    @property
    def priority(self) -> int:
        """优先级（数字越小越优先），默认 50。"""
        return 50
