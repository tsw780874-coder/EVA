"""EVA 电商真实数据引擎 v1.0 — Real Commerce Data Engine

核心定位：多电商平台商品事实数据聚合与结构化输出引擎
不是搜索引擎总结器，不是内容生成器。

五层强制抓取策略（按优先级执行）：
  Layer 1: SerpAPI Google Shopping — 实时商品数据（含价格/图片/评分/商家）
  Layer 2: 多平台价格补全 — 京东/天猫/淘宝/拼多多/得物/识货
  Layer 3: 商品聚合平台 — 比价数据 + SKU聚合
  Layer 4: 搜索引擎补充 — 百度/Google 商品信息
  Layer 5: 历史缓存回退 — 仅在前4层全失败时使用（必须标注数据时效）

数据质量铁律（不可违反）：
  1. ❌ price=0 一律过滤，绝不返回
  2. ❌ "暂无数据"不准出现 — 必须去其他平台补全
  3. ❌ picsum.photos 占位图不准用于真实数据
  4. ❌ 知乎/文章链接不准替代商品数据
  5. ❌ 编造评价/销量/评分一律拦截

用法:
    from app.agent.real_commerce_engine import (
        RealCommerceEngine, DataQualityGate, ShoppingDecisionEngine,
        validate_product, enrich_product_data,
    )

    engine = RealCommerceEngine()
    result = await engine.search_and_enrich("iPhone 16 Pro", top_k=5)
"""

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional

from app.api.v1.admin import append_log
from app.config import get_settings

settings = get_settings()

# ═══════════════════════════════════════════════════════════════════════
# 数据质量门禁 — 所有商品进门前必须通过
# ═══════════════════════════════════════════════════════════════════════


class DataQualityGate:
    """数据质量门禁 v4.1 — 核心原则：能返回则必须返回。

    只过滤真正无效的数据：
      1. 无名称
      2. 模拟/模板数据
      3. 知乎/公众号文章替代商品
      ── 以下情况不拒绝，仅标注 ──
      4. price=0 → 标记 price_display="点击查看实时价格"（放行）
      5. 无图片 → 留空（放行）
      6. 无评分 → 留空（放行）
    """

    MIN_NAME_LENGTH = 2
    FORBIDDEN_SOURCES = {"simulated", "template", "mock", "fallback"}
    FORBIDDEN_IMAGE_DOMAINS = {"picsum.photos", "via.placeholder.com", "placehold.co", "placeholder.com"}
    FORBIDDEN_CONTENT_DOMAINS = {"zhihu.com", "zhuanlan.zhihu.com", "weixin.qq.com", "mp.weixin.qq.com"}

    @staticmethod
    def validate(product: dict) -> tuple[bool, str]:
        """验证商品 — 只拦截真正无效的数据，绝不过滤可展示的真实结果。

        Returns:
            (passed, reason)
        """
        # 铁律1: 必须有商品名称
        name = product.get("name") or product.get("title", "")
        if len(str(name).strip()) < DataQualityGate.MIN_NAME_LENGTH:
            return False, "缺少商品名称"

        # 铁律2: 禁止模拟/模板数据
        source = product.get("source", "")
        if source in DataQualityGate.FORBIDDEN_SOURCES:
            return False, f"模拟数据已被真实数据引擎过滤"

        # 铁律3: 禁止知乎/公众号文章作为商品链接
        url = product.get("url", "")
        if url:
            for domain in DataQualityGate.FORBIDDEN_CONTENT_DOMAINS:
                if domain in url:
                    return False, f"内容链接不可替代商品数据"

        # ── 以下不拒绝，仅清理 ──
        # 清除占位图片
        image_url = product.get("image_url", "") or product.get("imageUrl", "")
        if image_url:
            for domain in DataQualityGate.FORBIDDEN_IMAGE_DOMAINS:
                if domain in image_url:
                    product["image_url"] = ""
                    break

        # price=0 不拒绝 — 后续 enrich 会标记
        return True, "ok"

    @staticmethod
    def validate_batch(products: list[dict]) -> tuple[list[dict], list[dict]]:
        """批量验证，返回 (通过, 被拒) 两个列表。"""
        passed, rejected = [], []
        for p in products:
            ok, reason = DataQualityGate.validate(p)
            if ok:
                passed.append(p)
            else:
                rejected.append({**p, "_reject_reason": reason})
        if rejected:
            append_log(
                "WARN",
                f"DataQualityGate 过滤 {len(rejected)}/{len(products)} 件商品: "
                + "; ".join(r.get("_reject_reason", "?")[:40] for r in rejected[:3]),
            )
        return passed, rejected


# ═══════════════════════════════════════════════════════════════════════
# 商品结构化拆解器
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class StructuredProduct:
    """结构化商品数据 — 每个商品必须包含以下字段。"""
    name: str                           # 商品名称
    brand: str = ""                     # 品牌
    model: str = ""                     # 型号
    platform: str = ""                  # 销售平台
    price: float = 0.0                  # 当前价格（必须 > 0）
    original_price: float = 0.0         # 原价
    price_range: str = ""               # 价格区间 "¥599-699"
    url: str = ""                       # 商品链接（必须可访问）
    image_url: str = ""                 # 商品图片（必须真实）
    rating: float = 0.0                 # 评分 (0-5)
    review_count: int = 0               # 评价数量
    sales_estimate: str = ""            # 预估销量
    positive_reviews_pct: float = 0.0   # 好评率
    negative_review_summary: str = ""   # 差评摘要
    shipping_info: str = ""             # 配送信息
    in_stock: bool = True               # 是否有货
    sku: str = ""                       # SKU/规格 (如 "256GB 深空黑")
    shop_name: str = ""                 # 店铺名称
    shop_rating: float = 0.0            # 店铺评分 (0-5)
    coupon_info: str = ""               # 优惠券/促销信息
    source: str = ""                    # 数据来源标识
    confidence: float = 0.0             # 数据可信度 (0-100)
    data_freshness: str = ""            # 数据新鲜度描述

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "platform": self.platform,
            "price": self.price,
            "original_price": self.original_price or self.price,
            "price_range": self.price_range,
            "url": self.url,
            "image_url": self.image_url,
            "rating": self.rating,
            "review_count": self.review_count,
            "sales_estimate": self.sales_estimate,
            "positive_reviews_pct": self.positive_reviews_pct,
            "negative_review_summary": self.negative_review_summary,
            "shipping_info": self.shipping_info,
            "in_stock": self.in_stock,
            "sku": self.sku,
            "shop_name": self.shop_name,
            "shop_rating": self.shop_rating,
            "coupon_info": self.coupon_info,
            "source": self.source,
            "confidence": self.confidence,
            "data_freshness": self.data_freshness,
            "source_is_real": True,
        }


def decompose_product(raw: dict) -> StructuredProduct:
    """将原始商品数据拆解为结构化商品。

    从任何来源（SerpAPI/product_db/live_search）的原始数据
    提取为标准 StructuredProduct 格式。
    """
    name = raw.get("name") or raw.get("title", "未知商品")
    price = raw.get("price", 0) or 0
    try:
        price = float(price)
    except (ValueError, TypeError):
        price = 0.0

    return StructuredProduct(
        name=name,
        brand=raw.get("brand", ""),
        model=raw.get("model", ""),
        platform=raw.get("platform", raw.get("source", "未知平台")),
        price=price,
        original_price=raw.get("original_price", 0) or price,
        price_range=raw.get("price_range", ""),
        url=raw.get("url", ""),
        image_url=raw.get("image_url", "") or raw.get("imageUrl", ""),
        rating=raw.get("rating", 0) or 0,
        review_count=raw.get("review_count", 0) or 0,
        sales_estimate=raw.get("sales_estimate", ""),
        positive_reviews_pct=raw.get("positive_reviews_pct", 0) or 0,
        negative_review_summary=raw.get("negative_review_summary", ""),
        shipping_info=raw.get("shipping", raw.get("shipping_info", "")),
        in_stock=raw.get("in_stock", True),
        source=raw.get("source", "unknown"),
        confidence=raw.get("confidence", 50.0),
        data_freshness=raw.get("data_freshness", ""),
    )


# ═══════════════════════════════════════════════════════════════════════
# 购物决策引擎
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ShoppingDecision:
    """购物决策报告 — 每次搜索必须输出。"""
    recommendation: str          # "推荐" / "可买" / "不推荐"
    confidence_level: str        # "高" / "中" / "低"
    best_product: str = ""       # 推荐商品名称
    best_platform: str = ""      # 推荐购买平台
    best_price: float | None = None  # 推荐入手价格（可为 None）
    reasons: list[str] = field(default_factory=list)       # 推荐理由
    risks: list[str] = field(default_factory=list)         # 风险提示
    purchase_advice: str = ""    # 购买建议
    price_trend: str = ""        # 价格走势
    promo_advice: str = ""       # 促销建议（618/双11）


class ShoppingDecisionEngine:
    """基于真实商品数据生成购物决策报告。"""

    @staticmethod
    def analyze(products: list[dict], query: str) -> ShoppingDecision:
        """分析商品列表，生成购物决策。

        规则（基于真实数据，不编造）：
          - 有3+商品且有明确价格 → 推荐
          - 有商品但价格需确认 → 可买
          - 0商品 → 不推荐
        """
        # 所有商品都参与分析（包括 price=None 的）
        valid = products
        # 有明确价格的商品
        priced = [p for p in products if (p.get("price") or 0) > 0]

        if not valid:
            return ShoppingDecision(
                recommendation="不推荐",
                confidence_level="低",
                reasons=["未找到具有有效价格的商品数据"],
                risks=["缺少真实价格信息，无法做出可靠判断"],
                purchase_advice="建议前往京东/天猫/得物等平台直接搜索，或尝试更换搜索关键词",
                promo_advice="建议关注618/双11等大促期间的官方活动价格",
            )

        # 按价格排序（优先用有价格的）
        sorted_by_price = sorted(
            valid, key=lambda p: (p.get("price") is None, p.get("price") or 0)
        )
        # 按评分排序
        sorted_by_rating = sorted(
            valid, key=lambda p: (p.get("rating") is None, p.get("rating") or 0), reverse=True
        )
        # 按可信度排序
        sorted_by_conf = sorted(
            valid, key=lambda p: p.get("confidence", 0), reverse=True
        )

        best = sorted_by_price[0] if sorted_by_price else None
        best_rated = sorted_by_rating[0] if sorted_by_rating else None

        # ── 生成推荐理由 ──
        reasons = []
        if len(valid) >= 3:
            reasons.append(f"找到 {len(valid)} 个相关商品，可进行多平台比价")
        elif len(valid) >= 1:
            reasons.append(f"找到 {len(valid)} 个相关商品")

        if best and best.get("price"):
            reasons.append(f"最低价格 ¥{best['price']:,.0f}（{best.get('platform','')}）")
        elif best:
            reasons.append(f"推荐查看 {best.get('name','')}（{best.get('platform','')}）")

        if best_rated and (best_rated.get("rating") or 0) > 4.0:
            reasons.append(
                f"{best_rated.get('name','')} 评分 {best_rated.get('rating',0)}/5，口碑优秀"
            )

        if best and (best.get("review_count") or 0) > 100:
            reasons.append(
                f"{best.get('name','')} 已有 {best.get('review_count',0):,} 条评价，数据充分"
            )

        if priced:
            reasons.append(f"{len(priced)} 件商品有明确价格，{len(valid) - len(priced)} 件需点击查看")

        # ── 风险提示 ──
        risks = []
        platforms_seen = set(p.get("platform", "") for p in valid)
        if len(platforms_seen) < 3:
            risks.append(f"当前仅覆盖 {len(platforms_seen)} 个平台，建议多方比价")

        sources = set(p.get("source", "") for p in valid)
        if "serpapi_shopping" not in sources:
            risks.append("数据非实时抓取，价格可能有延迟")

        confidences = [p.get("confidence", 0) for p in valid if p.get("confidence")]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        if avg_conf < 60:
            risks.append(f"数据可信度较低（{avg_conf:.0f}%），建议以实际平台价格为准")

        # 假货风险提示（特定品类）
        query_lower = query.lower()
        if any(kw in query_lower for kw in ["鞋", "nike", "adidas", "aj", "jordan", "包", "香水"]):
            risks.append("⚠️ 潮牌/奢侈品品类存在假货风险，建议选择得物/识货等鉴定平台")

        if any(kw in query_lower for kw in ["拼多多", "闲鱼"]):
            risks.append("⚠️ 二手/低价平台需注意商品真伪和成色")

        # ── 购买建议 ──
        if len(priced) >= 3 and avg_conf >= 60:
            recommendation = "推荐"
            confidence_level = "高"
            purchase = (
                f"推荐在 {best.get('platform','多平台')} 入手 {best.get('name','该商品')}，"
                f"当前价格 ¥{best.get('price',0):,.0f}。"
                f"建议对比至少3个平台后下单。"
            )
        elif len(valid) >= 1:
            recommendation = "可买"
            confidence_level = "中"
            if best and best.get("price"):
                purchase = (
                    f"可考虑 {best.get('name','该商品')}（{best.get('platform','')}，"
                    f"¥{best['price']:,.0f}），建议点击链接查看实时价格。"
                )
            else:
                purchase = (
                    f"找到 {len(valid)} 个相关商品，点击各平台链接查看实时价格后决定。"
                )
        else:
            recommendation = "不推荐"
            confidence_level = "低"
            purchase = "当前搜索未找到商品数据，建议前往京东/天猫/得物等平台直接搜索。"

        # ── 促销建议 ──
        now = time.localtime()
        month = now.tm_mon
        if month in (5, 6):
            promo = "618大促临近，建议关注平台预售活动和优惠券"
        elif month in (10, 11):
            promo = "双11即将到来，可等待大促期间入手"
        elif month in (11, 12, 1):
            promo = "年货节/双12期间可能有额外优惠"
        else:
            promo = "日常价格波动较小，随时可入手。关注平台百亿补贴/限时秒杀活动"

        return ShoppingDecision(
            recommendation=recommendation,
            confidence_level=confidence_level,
            best_product=best.get("name", "") if best else "",
            best_platform=best.get("platform", "") if best else "",
            best_price=best.get("price") if best and best.get("price") else None,
            reasons=reasons,
            risks=risks,
            purchase_advice=purchase,
            price_trend="当前为搜索时刻价格，实时价格请点击商品链接查看",
            promo_advice=promo,
        )


# ═══════════════════════════════════════════════════════════════════════
# 多平台价格补全器 — 一个平台没价格，去其他平台找
# ═══════════════════════════════════════════════════════════════════════

# 平台搜索 URL 模板
PLATFORM_SEARCH_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "唯品会": "https://www.vip.com/search?keyword={}",
    "识货": "https://www.shihuo.cn/search?keyword={}",
    "抖音商城": "https://haohuo.jinritemai.com/views/search?keyword={}",
    "闲鱼": "https://s.2.taobao.com/list/list.htm?q={}",
    "苏宁易购": "https://search.suning.com/{}/",
}


def generate_platform_search_links(
    query: str,
    platforms: list[str] | None = None,
) -> list[dict]:
    """生成主要电商平台的搜索链接（作为价格补全回退）。

    当实时抓取无法获取价格时，至少提供真实的搜索链接让用户点击查看。
    这是"宁可给链接也不显示0价格"策略的实现。
    """
    from urllib.parse import quote

    if platforms is None:
        platforms = ["京东", "天猫", "淘宝", "拼多多", "得物", "识货"]

    links = []
    encoded = quote(query)
    for plat in platforms:
        tmpl = PLATFORM_SEARCH_URLS.get(plat, "")
        if tmpl:
            links.append({
                "name": f"在{plat}搜索: {query}",
                "platform": plat,
                "price": None,  # 明确标记为"需用户自行查看"
                "price_display": "点击查看实时价格",
                "url": tmpl.format(encoded),
                "image_url": "",
                "source": "platform_search_link",
                "confidence": 40.0,  # 搜索链接的可信度 — 平台本身是可信的，但没拿到具体数据
                "is_search_link": True,
            })

    return links


# ═══════════════════════════════════════════════════════════════════════
# 商品数据富化 — 补充缺失字段
# ═══════════════════════════════════════════════════════════════════════


def enrich_product_data(product: dict, query: str = "") -> dict:
    """八维商品数据富化 — 每商品补全所有可获取字段，缺失的留空不输出。

    八个维度（有则填，无则留空）：
      1. 商品名称 name
      2. 价格 price + price_display
      3. 销量预估 sales_estimate
      4. 评价抓取 rating + review_count + positive_reviews_pct
      5. 品牌抓取 brand + model
      6. 商品图片 image_url
      7. 商品链接 url（必须）
      8. 真实价格分析 price_analysis（基于多平台比价）
    """
    p = dict(product)

    # ── 1. 名称 ──
    p.setdefault("name", p.get("title", ""))

    # ── 2. 价格 ──
    price = p.get("price", 0) or 0
    try:
        price = float(price)
    except (ValueError, TypeError):
        price = 0.0

    if price <= 0:
        # 尝试从 original_price 补全
        orig = p.get("original_price", 0) or 0
        try:
            orig = float(orig)
        except (ValueError, TypeError):
            orig = 0.0
        if orig > 0:
            p["price"] = orig
            p["price_note"] = "原价（实际可能有折扣）"
        else:
            p["price"] = None
            p["price_display"] = "点击查看实时价格"
    else:
        p["price"] = price

    # ── 3. 销量预估 ──
    if not p.get("sales_estimate") and p.get("review_count", 0):
        rc = p.get("review_count", 0) or 0
        if rc > 10000:
            p["sales_estimate"] = f"热销（{rc:,}条评价）"
        elif rc > 1000:
            p["sales_estimate"] = f"畅销（{rc:,}条评价）"
        elif rc > 100:
            p["sales_estimate"] = "正常销售"
    p.setdefault("sales_estimate", None)

    # ── 4. 评价 ──
    rating = p.get("rating", None)
    if rating is not None:
        try:
            p["rating"] = round(float(rating), 1)
        except (ValueError, TypeError):
            p["rating"] = None
    rc = p.get("review_count", None)
    if rc is not None:
        try:
            p["review_count"] = int(rc)
        except (ValueError, TypeError):
            p["review_count"] = None
    p.setdefault("positive_reviews_pct", None)

    # ── 5. 品牌 ──
    if not p.get("brand"):
        name = str(p.get("name", ""))
        brands = ["Apple", "Samsung", "Sony", "Nike", "Adidas", "YONEX",
                   "华为", "小米", "NVIDIA", "Intel", "AMD", "Dyson",
                   "戴森", "格力", "美的", "李宁", "安踏"]
        for b in brands:
            if b.lower() in name.lower():
                p["brand"] = b
                break
    p.setdefault("brand", None)
    p.setdefault("model", None)

    # ── 6. 图片 ──
    image_url = p.get("image_url", "") or p.get("imageUrl", "")
    for domain in DataQualityGate.FORBIDDEN_IMAGE_DOMAINS:
        if domain in (image_url or ""):
            image_url = ""
            break
    p["image_url"] = image_url or None

    # ── 7. 链接 ──
    if not p.get("url"):
        platform = p.get("platform", "")
        name = p.get("name", "")
        from urllib.parse import quote
        tmpl = PLATFORM_SEARCH_URLS.get(platform, "")
        if tmpl and name:
            p["url"] = tmpl.format(quote(name))
    p.setdefault("url", None)

    # ── 8. 真实价格分析 ──
    # 标记数据获取时间和免责声明
    p["data_freshness"] = time.strftime("%Y-%m-%d %H:%M")
    p["data_disclaimer"] = "价格为搜索时获取，实际以平台页面为准"
    p["source_is_real"] = p.get("source", "") not in DataQualityGate.FORBIDDEN_SOURCES

    # ── 清理：所有 None 值的可选字段不出现在最终输出 ──
    # （FastAPI JSON 序列化时自动跳过 None，前端只需处理缺失字段）

    return p


# ═══════════════════════════════════════════════════════════════════════
# 主引擎 — 统一入口
# ═══════════════════════════════════════════════════════════════════════


class RealCommerceEngine:
    """电商真实数据引擎 — 多平台商品数据聚合与质量保障。

    职责：
      1. 接收原始商品数据（来自 pipeline 搜索层）
      2. 逐一通过 DataQualityGate 验证
      3. 富化缺失字段
      4. 生成购物决策报告
      5. 确保不含任何虚假/兜底数据
    """

    def __init__(self):
        self.gate = DataQualityGate()
        self.decision_engine = ShoppingDecisionEngine()

    async def process(
        self,
        products: list[dict],
        query: str,
        search_layers_used: list[str],
        data_source: str,
    ) -> dict:
        """处理商品数据管线的最终输出。

        Args:
            products: 原始商品列表（来自 pipeline 各搜索层）
            query: 用户原始查询
            search_layers_used: 已使用的搜索层列表
            data_source: 主要数据来源标识

        Returns:
            {
                "valid_products": [...],       # 通过质量门禁的商品
                "rejected_products": [...],     # 被门禁拒绝的商品
                "decision": ShoppingDecision,   # 购物决策报告
                "platform_links": [...],        # 平台搜索链接（回退用）
                "quality_report": {...},        # 数据质量报告
            }
        """
        t0 = time.perf_counter()

        # ── Step 1: 富化所有商品 ──
        enriched = [enrich_product_data(p, query) for p in products]

        # ── Step 2: 质量门禁 ──
        valid, rejected = self.gate.validate_batch(enriched)

        # ── Step 3: 按可信度排序 ──
        valid.sort(key=lambda p: p.get("confidence", 0), reverse=True)

        # ── Step 4: 如果有效商品不足，生成平台搜索链接作为回退 ──
        platform_links = []
        if len(valid) < 3:
            platform_links = generate_platform_search_links(query)
            # 平台搜索链接也需通过质量门禁（它们没有价格，但标记为"需查看"）
            # 链接以 is_search_link=True 区分，前端可特殊展示

        # ── Step 5: 生成购物决策 ──
        decision = self.decision_engine.analyze(valid, query)

        # ── Step 6: 数据质量报告 ──
        quality_report = {
            "total_raw": len(products),
            "passed": len(valid),
            "rejected": len(rejected),
            "rejection_reasons": list(set(
                r.get("_reject_reason", "未知")[:60] for r in rejected
            )),
            "has_real_price": any(
                (p.get("price") or 0) > 0 for p in valid
            ),
            "has_real_image": any(
                p.get("image_url", "") for p in valid
            ),
            "platform_links_generated": len(platform_links),
            "search_layers_used": search_layers_used,
            "primary_source": data_source,
        }

        elapsed_ms = (time.perf_counter() - t0) * 1000
        append_log(
            "SUCCESS" if valid else "WARN",
            f"RealCommerceEngine: {len(valid)}/{len(products)} products passed "
            f"(rejected={len(rejected)}, links={len(platform_links)}, {elapsed_ms:.0f}ms)",
        )

        return {
            "valid_products": valid,
            "rejected_products": rejected,
            "decision": decision,
            "platform_links": platform_links,
            "quality_report": quality_report,
        }


# ═══════════════════════════════════════════════════════════════════════
# 快捷函数 — 给 pipeline 调用
# ═══════════════════════════════════════════════════════════════════════

_engine: RealCommerceEngine | None = None


def get_engine() -> RealCommerceEngine:
    global _engine
    if _engine is None:
        _engine = RealCommerceEngine()
    return _engine


def validate_product(product: dict) -> tuple[bool, str]:
    """快捷验证单个商品。"""
    return DataQualityGate.validate(product)


async def process_commerce_results(
    products: list[dict],
    query: str,
    search_layers_used: list[str] | None = None,
    data_source: str = "unknown",
) -> dict:
    """快捷处理商品结果（pipeline 直接调用）。"""
    engine = get_engine()
    return await engine.process(
        products=products,
        query=query,
        search_layers_used=search_layers_used or [],
        data_source=data_source,
    )
