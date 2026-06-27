"""多多客 (Pinduoduo Duoduo Alliance) API 适配器。

官方 API: pdd.ddk.goods.search
文档: https://open.pinduoduo.com/application/document/api?id=pdd.ddk.goods.search

需要配置环境变量:
  PDD_CLIENT_ID=xxx
  PDD_CLIENT_SECRET=xxx
  PDD_PID=xxx

未配置时 is_available() 返回 False，自动跳过。
"""

import hashlib
import time
from app.agent.platform_adapters.base import ProductSearchAdapter, ProductSearchResult
from app.config import get_settings


class PddAffiliateAdapter(ProductSearchAdapter):
    """拼多多多多客商品搜索适配器。"""

    def __init__(self):
        settings = get_settings()
        self.client_id: str = getattr(settings, "pdd_client_id", "") or ""
        self.client_secret: str = getattr(settings, "pdd_client_secret", "") or ""
        self.pid: str = getattr(settings, "pdd_pid", "") or ""
        self._api_url = "https://gw-api.pinduoduo.com/api/router"

    @property
    def source_name(self) -> str:
        return "pdd_affiliate"

    @property
    def priority(self) -> int:
        return 20

    def is_available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _sign(self, params: dict) -> str:
        """拼多多 API MD5 签名。"""
        sorted_keys = sorted(params.keys())
        sign_str = self.client_secret + "".join(
            f"{k}{params[k]}" for k in sorted_keys
        ) + self.client_secret
        return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()

    async def search(
        self,
        query: str,
        top_k: int = 5,
        timeout: float = 10.0,
    ) -> list[ProductSearchResult]:
        if not self.is_available():
            return []

        try:
            import httpx, json

            params = {
                "type": "pdd.ddk.goods.search",
                "client_id": self.client_id,
                "timestamp": str(int(time.time())),
                "data_type": "JSON",
                "keyword": query,
                "page_size": str(top_k),
                "page": "1",
                "pid": self.pid,
                "sort_type": 0,  # 0=综合排序
            }
            params["sign"] = self._sign(params)

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self._api_url, json=params)
                resp.raise_for_status()
                data = resp.json()

            results: list[ProductSearchResult] = []
            items = (
                data.get("goods_search_response", {})
                .get("goods_list", [])
            )

            for item in items[:top_k]:
                price = item.get("min_group_price", item.get("min_normal_price", 0))
                results.append(ProductSearchResult(
                    name=item.get("goods_name", ""),
                    price=float(price) / 100 if price else 0,  # PDD 金额单位为分
                    original_price=float(item.get("min_normal_price", 0)) / 100 if item.get("min_normal_price") else 0.0,
                    platform="拼多多",
                    url=item.get("url", item.get("mobile_url", "")),
                    image_url=item.get("goods_image_url", item.get("goods_thumbnail_url", "")),
                    rating=None,
                    review_count=int(item.get("sales_tip", "0").replace("已拼", "").replace("万件", "0000").replace("件", "")) if item.get("sales_tip") else 0,
                    shipping_info="",
                    in_stock=bool(item.get("has_coupon", True)),
                    brand=item.get("mall_name", ""),
                    source=self.source_name,
                    confidence=70.0,
                    raw_data=item,
                ))

            return results

        except ImportError:
            return []
        except Exception:
            return []
