"""淘宝客 (Taobao Alliance) API 适配器。

官方 API: taobao.tbk.dg.material.optional
文档: https://open.taobao.com/api.htm

需要配置环境变量:
  TAOBAO_APP_KEY=xxx
  TAOBAO_APP_SECRET=xxx
  TAOBAO_ADZONE_ID=xxx

未配置时 is_available() 返回 False，自动跳过。
"""

import hashlib
import time
from app.agent.platform_adapters.base import ProductSearchAdapter, ProductSearchResult
from app.config import get_settings


class TaobaoAffiliateAdapter(ProductSearchAdapter):
    """淘宝客商品搜索适配器。

    使用 HTTPS POST 请求 taobao.tbk.dg.material.optional 接口。
    """

    def __init__(self):
        settings = get_settings()
        self.app_key: str = getattr(settings, "taobao_app_key", "") or ""
        self.app_secret: str = getattr(settings, "taobao_app_secret", "") or ""
        self.adzone_id: str = getattr(settings, "taobao_adzone_id", "") or ""
        self._api_url = "https://eco.taobao.com/router/rest"

    @property
    def source_name(self) -> str:
        return "taobao_affiliate"

    @property
    def priority(self) -> int:
        return 15

    def is_available(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def _sign(self, params: dict) -> str:
        """淘宝 API MD5 签名。"""
        sorted_keys = sorted(params.keys())
        sign_str = self.app_secret + "".join(
            f"{k}{params[k]}" for k in sorted_keys if k != "sign"
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
            import httpx, json

            params = {
                "method": "taobao.tbk.dg.material.optional",
                "app_key": self.app_key,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "format": "json",
                "v": "2.0",
                "sign_method": "md5",
                "adzone_id": self.adzone_id,
                "q": query,
                "page_size": str(top_k),
                "page_no": "1",
                "platform": "2",  # 2=不限平台（含天猫）
            }
            params["sign"] = self._sign(params)

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    self._api_url,
                    data=params,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                data = resp.json()

            results: list[ProductSearchResult] = []
            items = (
                data.get("tbk_dg_material_optional_response", {})
                .get("result_list", {})
                .get("map_data", [])
            )

            for item in items[:top_k]:
                price = item.get("zk_final_price", item.get("reserve_price", 0))
                platform = "天猫" if item.get("user_type") == 1 else "淘宝"
                results.append(ProductSearchResult(
                    name=item.get("title", ""),
                    price=float(price) if price else 0,
                    original_price=float(item.get("reserve_price", 0)) if item.get("reserve_price") else 0.0,
                    platform=platform,
                    url=item.get("coupon_share_url", item.get("click_url", "")),
                    image_url=item.get("pict_url", ""),
                    rating=None,
                    review_count=int(item.get("volume", 0)) if item.get("volume") else 0,
                    shipping_info=item.get("delivery_info", ""),
                    in_stock=True,
                    brand=item.get("shop_title", ""),
                    source=self.source_name,
                    confidence=75.0,
                    raw_data=item,
                ))

            return results

        except ImportError:
            return []
        except Exception:
            return []
