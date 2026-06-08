"""Direct async shopping pipeline — no LangGraph, single LLM call.

Replaces the old StateGraph with 5 nodes + supervisor with a single
async function.  Search + review are fused into one LLM call so
total LLM round-trips drop from 2 → 1.  Token streaming goes through
a simple async callback — no queues, no racing, no overhead.
"""

import hashlib
import json
import re
import time
import uuid
from functools import lru_cache
from typing import Callable, Awaitable
from urllib.parse import quote

from app.agent.llm_utils import llm_call
from app.agent.product_templates import match_template
from app.api.v1.admin import append_log

# ---------------------------------------------------------------------------
# Product enrichment (unchanged from search.py)
# ---------------------------------------------------------------------------

PLATFORM_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
}

PRODUCT_IMAGE_POOL = {
    "耳机": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop",
    "蓝牙": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop",
    "手机": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop",
    "iPhone": "https://images.unsplash.com/photo-1512054502232-10a0a035e672?w=400&h=400&fit=crop",
    "笔记本": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop",
    "平板": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop",
    "相机": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=400&h=400&fit=crop",
    "手表": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop",
    "鞋": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop",
    "美妆": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=400&h=400&fit=crop",
    "护肤": "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=400&h=400&fit=crop",
    "包": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop",
    "香水": "https://images.unsplash.com/photo-1541643600914-78b084683601?w=400&h=400&fit=crop",
    "电视": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=400&h=400&fit=crop",
    "音箱": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=400&h=400&fit=crop",
    "键盘": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=400&h=400&fit=crop",
    "鼠标": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=400&h=400&fit=crop",
    "显示器": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=400&h=400&fit=crop",
    "显卡": "https://images.unsplash.com/photo-1591488320449-011701bb9704?w=400&h=400&fit=crop",
    "游戏机": "https://images.unsplash.com/photo-1486401899868-0e435ed85128?w=400&h=400&fit=crop",
    "Switch": "https://images.unsplash.com/photo-1578303512597-81e6cc155b3e?w=400&h=400&fit=crop",
    "PS5": "https://images.unsplash.com/photo-1606811841689-23dfddce3e95?w=400&h=400&fit=crop",
    "家电": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=400&h=400&fit=crop",
    "床垫": "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=400&h=400&fit=crop",
    "家具": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400&h=400&fit=crop",
    "灯": "https://images.unsplash.com/photo-1507473885765-e6ed057ab6fe?w=400&h=400&fit=crop",
    "default": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=400&h=400&fit=crop",
}


@lru_cache(maxsize=512)
def _pick_image(name: str) -> str:
    for keyword, url in PRODUCT_IMAGE_POOL.items():
        if keyword in name:
            return url
    seed = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"https://picsum.photos/seed/{seed}/400/400"


def _enrich_product(p: dict) -> dict:
    name = p.get("name", "未知")
    platform = p.get("platform", "未知")
    seed = f"{name}_{platform}"
    pid = str(uuid.UUID(hashlib.md5(seed.encode()).hexdigest()))
    url = p.get("url", "")
    if not url:
        tmpl = PLATFORM_URLS.get(platform)
        if tmpl:
            url = tmpl.format(quote(name))
    image_url = p.get("image_url", "") or p.get("imageUrl", "")
    if not image_url or "example.com" in image_url or "placeholder" in image_url.lower():
        image_url = _pick_image(name)
    p["id"] = pid
    p["url"] = url
    p["image_url"] = image_url
    for field in ("price", "original_price", "rating"):
        if field in p and p[field] is not None:
            try:
                p[field] = float(p[field])
            except (ValueError, TypeError):
                pass
    return p


# ---------------------------------------------------------------------------
# Intent classification (keyword-based, < 1 ms)
# ---------------------------------------------------------------------------

_SHOPPING_KEYWORDS = [
    "价格", "比价", "对比", "最低价", "推荐", "哪个平台", "性价比",
    "便宜", "买", "多少钱", "哪里买", "哪家", "划算", "折扣", "优惠",
    "降价", "促销", "秒杀", "特价", "最低", "最便宜", "报价", "价位",
    "入手", "下单", "购买", "采购", "代购", "海淘", "网购",
    "耳机", "手机", "笔记本", "平板", "相机", "手表", "键盘", "鼠标",
    "显示器", "显卡", "游戏机", "音箱", "电视", "家电", "家具", "床垫",
    "美妆", "护肤", "香水", "鞋", "包", "灯", "Switch", "PS5",
    "price", "compare", "cheap", "best", "buy", "deal", "discount",
    "shop", "purchase", "order", "recommend", "review", "rating",
    "lowest", "affordable", "worth", "vs", "versus",
]

_COMPLAINT_KEYWORDS = [
    "投诉", "维权", "退款", "退货", "假货", "质量问题", "差评",
    "客服", "欺骗", "上当", "坑", "投诉电话", "12315",
    "complaint", "refund", "return", "fake", "scam", "broken",
]

_PRODUCT_QUERY_KEYWORDS = [
    "参数", "规格", "配置", "尺寸", "重量", "材质", "功能",
    "续航", "待机", "存储", "内存", "处理器", "芯片", "像素",
    "spec", "specs", "specification", "warranty", "size", "weight",
]


def classify_intent(query: str) -> str:
    q = query.lower()
    if any(kw in q for kw in _SHOPPING_KEYWORDS):
        return "shopping"
    if any(kw in q for kw in _COMPLAINT_KEYWORDS):
        return "complaint"
    if any(kw in q for kw in _PRODUCT_QUERY_KEYWORDS):
        return "product_query"
    return "general"


# ---------------------------------------------------------------------------
# Single combined LLM call: products + reviews
# ---------------------------------------------------------------------------

_COMBINED_PROMPT = (
    "你是电商购物专家。根据用户查询，完成以下两个任务："
    "1. 生成3个不同平台的模拟商品（name/platform/price/original_price/rating/review_count）"
    "2. 给出该商品的优缺点各2条和购买建议"
    '返回JSON: {"products":[...], "review":{"pros":[],"cons":[],"verdict":""}}'
    "价格用人民币，JSON放在```json代码块中。"
)


async def search_and_review(
    query: str,
    user_id: str = "",
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[list[dict], dict]:
    """Combined search + review in a single LLM call.

    Returns (products, review_summary).  On failure returns ([], {}).
    """
    content, provider = await llm_call(
        system_prompt=_COMBINED_PROMPT,
        user_message=f"查询:{query}",
        max_tokens=500,
        temperature=0.3,
        user_id=user_id,
        node_name="search_review",
        stream_callback=stream_callback,
    )

    if not content:
        return [], {}

    try:
        match = re.search(r"```json\s*([\s\S]*?)```", content)
        data = json.loads(match.group(1) if match else content)
        products_raw = data.get("products", [])
        review = data.get("review", {})
    except Exception:
        return [], {}

    products = [_enrich_product(p) for p in products_raw]
    return products, review


# ---------------------------------------------------------------------------
# Pure-compute nodes (zero LLM, zero I/O)
# ---------------------------------------------------------------------------

def compute_price_analysis(products: list[dict]) -> dict:
    if not products:
        return {}
    prices = [(p["platform"], p["price"], p.get("original_price", p["price"])) for p in products]
    sorted_prices = sorted(prices, key=lambda x: x[1])
    best = sorted_prices[0]
    return {
        "best_price": best[1],
        "best_platform": best[0],
        "average_price": round(sum(p[1] for p in prices) / len(prices), 2),
        "price_range": f"¥{sorted_prices[0][1]} - ¥{sorted_prices[-1][1]}",
        "max_discount": max(
            ((orig - price) / orig * 100 for _, price, orig in prices if orig > price),
            default=0,
        ),
        "platforms": [{"name": p[0], "price": p[1], "original": p[2]} for p in prices],
    }


def compute_decision(price_analysis: dict, review_summary: dict) -> dict:
    if not price_analysis or review_summary.get("error"):
        return {
            "recommendation": "insufficient_data",
            "best_platform": "数据不足",
            "best_price": 0,
            "rating": 0,
            "confidence": 0,
            "reason": "商品搜索或评论分析未能获取到真实数据，无法做出购买决策。请稍后重试。",
        }

    best_price = price_analysis.get("best_price", 0)
    best_platform = price_analysis.get("best_platform", "未知")
    verdict = review_summary.get("verdict", "")
    pros = review_summary.get("pros", [])
    cons = review_summary.get("cons", [])

    rating = min(3 + len(pros) * 0.5, 5.0)
    rating = max(rating - len(cons) * 0.3, 1.0)
    should_buy = rating >= 4.0 and best_price > 0

    return {
        "recommendation": "buy" if should_buy else "consider",
        "best_platform": best_platform,
        "best_price": best_price,
        "rating": round(rating, 1),
        "confidence": round(min(rating / 5, 1.0), 2),
        "reason": (
            f"该商品在{best_platform}以¥{best_price}的价格销售，综合评分{rating:.1f}/5，{verdict}。建议购买。"
            if should_buy
            else f"该商品评价一般（{rating:.1f}/5），建议慎重考虑或寻找替代品。"
        ),
    }


def generate_report(
    products: list[dict],
    price_analysis: dict,
    review_summary: dict,
    decision: dict,
    user_query: str,
) -> str:
    lines = [f"## {user_query}", ""]

    if price_analysis and products:
        lines.append(
            f"**最佳价格**：{price_analysis.get('best_platform','?')} "
            f"¥{price_analysis.get('best_price',0):,.0f}"
            f"（均价 ¥{price_analysis.get('average_price',0):,.0f}）"
        )
        lines.append("")

    if review_summary:
        verdict = review_summary.get("verdict", "")
        pros = review_summary.get("pros", [])
        cons = review_summary.get("cons", [])
        parts = []
        if pros:
            parts.append("优点：" + "；".join(pros))
        if cons:
            parts.append("缺点：" + "；".join(cons))
        if parts:
            lines.append(" | ".join(parts))
        if verdict:
            lines.append(f"**口碑**：{verdict}")
        lines.append("")

    if decision:
        rec = decision.get("recommendation", "")
        if rec == "buy":
            lines.append(f"> ✅ 推荐购买 — {decision.get('reason','')}")
        elif rec == "insufficient_data":
            lines.append(f"> ⚠️ 数据不足 — {decision.get('reason','')}")
        else:
            lines.append(f"> ⚠️ 慎重考虑 — {decision.get('reason','')}")

    lines.append("")
    lines.append("*EVA Agent 智能生成 | 数据仅供参考*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Query-level cache
# ---------------------------------------------------------------------------

_result_cache: dict[str, tuple[float, dict]] = {}
_RESULT_CACHE_TTL = 600  # 10 minutes


def _result_cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

async def run_pipeline(
    user_query: str,
    user_id: str = "",
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
    bypass_cache: bool = False,
) -> dict:
    """Run the complete shopping pipeline and return all results.

    Returns a dict with: intent, search_results, price_analysis,
    review_summary, decision, final_report.

    LLM calls: exactly 1 (combined search+review).
    """
    t0 = time.perf_counter()

    # --- Query-level cache ---
    rk = _result_cache_key(user_query)
    if not bypass_cache and rk in _result_cache:
        expiry, cached = _result_cache[rk]
        if time.time() < expiry:
            append_log("INFO", f"pipeline 命中查询缓存 ({user_query[:30]}...)")
            if stream_callback:
                await stream_callback(cached.get("final_report", ""))
            return cached

    # --- Intent ---
    intent = classify_intent(user_query)

    # --- Search + Review: template first (< 1ms), LLM fallback ---
    products: list[dict] = []
    review: dict = {}

    if intent in ("shopping", "product_query"):
        # 1st — try instant template match
        template = match_template(user_query)
        if template is not None:
            products, review = template
            append_log("INFO", f"pipeline 模板命中 ({len(products)}件商品, < 1ms)")
            # Stream template data as tokens for frontend
            if stream_callback:
                await stream_callback(json.dumps({"products": products, "review": review}, ensure_ascii=False))
        else:
            # 2nd — LLM with racing (Groq LPU first, ~200-800ms)
            products, review = await search_and_review(user_query, user_id, stream_callback)
            if not products:
                # 3rd — ultimate fallback: generic template
                template = match_template("推荐")
                if template:
                    products, review = template
                    append_log("WARN", "pipeline LLM失败，使用通用模板")
    else:
        products, review = [], {}

    # --- Pure compute (instant) ---
    price_analysis = compute_price_analysis(products)
    decision = compute_decision(price_analysis, review)
    final_report = generate_report(products, price_analysis, review, decision, user_query)

    result = {
        "intent": intent,
        "search_results": products,
        "price_analysis": price_analysis,
        "review_summary": review,
        "decision": decision,
        "final_report": final_report,
    }

    _result_cache[rk] = (time.time() + _RESULT_CACHE_TTL, result)

    elapsed = (time.perf_counter() - t0) * 1000
    append_log("SUCCESS", f"pipeline 完成 ({elapsed:.0f}ms) intent={intent} products={len(products)}")

    return result
