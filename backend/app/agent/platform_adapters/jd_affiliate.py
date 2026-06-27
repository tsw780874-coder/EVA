"""京东联盟 (JD Union) Affiliate API 适配器。

官方 API: jd.union.open.goods.query
文档: https://union.jd.com/openplatform/api

需要配置环境变量:
  JD_UNION_APP_KEY=xxx
  JD_UNION_APP_SECRET=xxx
  JD_UNION_SITE_ID=xxx

未配置时 is_available() 返回 False，自动跳过。
"""

import hashlib
import time
from typing import Optional
from app.agent.platform_adapters.base import ProductSearchAdapter, ProductSearchResult
from app.config import get_settings


class JdAffiliateAdapter(ProductSearchAdapter):
    """京东联盟商品搜索适配器。

    使用 HTTPS GET 请求 jd.union.open.goods.query 接口。
    """

    def __init__(self):
        settings = get_settings()
        self.app_key: str = getattr(settings, "jd_union_app_key", "") or ""
        self.app_secret: str = getattr(settings, "jd_union_app_secret", "") or ""
        self.site_id: str = getattr(settings, "jd_union_site_id", "") or ""
        self._api_url = "https://router.jd.com/api"

    @property
    def source_name(self) -> str:
        return "jd_affiliate"

    @property
    def priority(self) -> int:
        return 10  # 最高优先级

    def is_available(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def _sign(self, params: dict) -> str:
        """京东 API 签名算法。"""
        sorted_keys = sorted(params.keys())
        sign_str = self.app_secret + "".join(
            f"{k}{params[k]}" for k in sorted_keys
        ) + self.app_secret
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
            import httpx

            params = {
                "method": "jd.union.open.goods.query",
                "app_key": self.app_key,
                "access_token": "",
                "format": "json",
                "v": "1.0",
                "sign_method": "md5",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "param_json": __import__("json").dumps({
                    "goodsReqDTO": {
                        "keyword": query,
                        "pageSize": top_k,
                        "pageIndex": 1,
                    }
                }),
            }
            params["sign"] = self._sign(params)

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self._api_url, data=params)
                resp.raise_for_status()
                data = resp.json()

            results: list[ProductSearchResult] = []
            goods_list = (
                data.get("jd_union_open_goods_query_response", {})
                .get("queryResult", {})
                .get("result", [])
            )
            if isinstance(goods_list, str):
                goods_list = __import__("json").loads(goods_list)

            for item in goods_list[:top_k]:
                price = item.get("price", item.get("wlPrice", 0))
                results.append(ProductSearchResult(
                    name=item.get("goodsName", item.get("skuName", "")),
                    price=float(price) if price else 0,
                    original_price=float(item.get("price", 0)) if item.get("price") else 0.0,
                    platform="京东",
                    url=item.get("materialUrl", item.get("goodCommentsShare", "")),
                    image_url=item.get("imageUrl", item.get("imgUrl", "")),
                    rating=float(item.get("goodRate", 0)) if item.get("goodRate") else None,
                    review_count=int(item.get("comments", 0)) if item.get("comments") else 0,
                    shipping_info=item.get("delivery", ""),
                    in_stock=item.get("stockState", 1) == 1,
                    brand=item.get("brandName", ""),
                    source=self.source_name,
                    confidence=75.0,  # 官方API，高置信度
                    raw_data=item,
                ))

            return results

        except ImportError:
            return []
        except Exception:
            return []
