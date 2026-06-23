"""v6 Multi-Layer Shopping Pipeline — always returns real products.

v6 architecture (5-layer search strategy):
  User → Intent → Query Rewrite → RAG → Product Cache → Live Search
  → Similar Search → Template → (only then) not_found

Key principles:
  1. Always try to return at least 1 real product.
  2. not_found is the absolute LAST resort — only when all 5 layers fail.
  3. Every product includes confidence scores and source attribution.
  4. Progressive degradation: exact → similar → category → brand.
  5. NEVER fabricate price/stock/reviews. Mark simulated data clearly.
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
from app.agent.model_router import route_query
from app.agent.query_rewriter import rewrite_query, degrade_query
from app.api.v1.admin import append_log
from app.core.perf import get_timer
from app.core.citations import CitationTracker
from app.core.confidence import ConfidenceScorer
from app.core.verifier import DataVerifier

# ---------------------------------------------------------------------------
# Product enrichment (only adds formatting, never invents data)
# ---------------------------------------------------------------------------

PLATFORM_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
}


@lru_cache(maxsize=512)
def _pick_image(name: str) -> str:
    seed = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"https://picsum.photos/seed/{seed}/400/400"


def _enrich_product(p: dict) -> dict:
    """Format product dict consistently. Never invents core data."""
    name = p.get("name", "未知")
    platform = p.get("platform", "未知")
    seed = f"{name}_{platform}"
    pid = p.get("id") or str(uuid.UUID(hashlib.md5(seed.encode()).hexdigest()))

    url = p.get("url", "")
    if not url:
        tmpl = PLATFORM_URLS.get(platform)
        if tmpl:
            url = tmpl.format(quote(name))

    image_url = p.get("image_url", "") or p.get("imageUrl", "")
    if not image_url:
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

    # Ensure source field exists
    if "source" not in p:
        p["source"] = p.get("source", "rag")
    if "confidence" not in p:
        p["confidence"] = p.get("confidence", 50.0)

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
    "空调", "冰箱", "洗衣机", "扫地", "吸尘器",
    "iPhone", "iPad", "MacBook", "AirPods", "Apple Watch",
    "Galaxy", "ThinkPad", "XPS", "ROG", "PlayStation", "Xbox",
    "RTX", "GeForce", "Radeon", "Ryzen", "Intel",
    "YONEX", "yonex", "Victor", "Li-Ning", "Nike", "Adidas",
    "羽毛球拍", "羽球拍", "球拍", "羽毛球", "网球拍",
    "篮球", "足球", "跑步鞋", "跑鞋", "运动鞋",
    "天斧", "弓箭", "疾光", "双刃", "龙牙", "雷霆", "神速",
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
    if any(kw.lower() in q for kw in _SHOPPING_KEYWORDS):
        return "shopping"
    if any(kw.lower() in q for kw in _COMPLAINT_KEYWORDS):
        return "complaint"
    if any(kw.lower() in q for kw in _PRODUCT_QUERY_KEYWORDS):
        return "product_query"
    return "general"


# ---------------------------------------------------------------------------
# Anti-hallucination prompts (v6 — progressive search, never fabricate)
# ---------------------------------------------------------------------------

_QUICK_CHAT_PROMPT = (
    "你是一个友好的AI购物助手。如果问题涉及具体商品信息（价格、参数、评价），"
    "请基于提供的上下文回答，不要凭记忆编造数据。"
    "用中文简洁回复，2-3句话。"
)

# RAG-context prompt: LLM only SUMMARIZES, never generates product data
_RAG_SUMMARIZE_PROMPT = (
    "你是电商购物专家。请基于以下检索到的商品数据，回答用户问题。\n"
    "规则：\n"
    "1. 只使用下方提供的商品信息，不要凭自己的记忆补充价格或参数\n"
    "2. 如实呈现商品信息，标注数据来源\n"
    "3. 用中文回复，结构清晰，突出关键信息（价格、平台、推荐理由）"
)

# Multi-source prompt: products found from cache/live search
_MULTI_SOURCE_PROMPT = (
    "你是电商购物专家。以下是通过多种渠道找到的商品信息。\n"
    "规则：\n"
    "1. 如实呈现这些商品，标注每个商品的来源\n"
    "2. 按价格从低到高排列，突出最优选择\n"
    "3. 提醒用户数据可能有时效性，建议点击链接查看最新价格\n"
    "4. 用中文回复，结构清晰"
)

# Degraded result prompt: found similar products, not exact match
_SIMILAR_PROMPT = (
    "你是电商购物专家。未能找到用户查询的精确商品，但找到了以下相似或相关商品。\n"
    "规则：\n"
    "1. 诚实告知用户未找到精确匹配，但展示了最接近的替代选择\n"
    "2. 解释为什么这些是相似的（同品牌、同系列、同类别等）\n"
    "3. 建议用户尝试更具体的搜索词或访问电商平台直接搜索\n"
    "4. 用中文回复，友好且实用"
)

# Fallback: absolutely no data found anywhere
_NO_DATA_PROMPT = (
    "你是电商购物专家。经过多渠道搜索（知识库、商品缓存、电商平台），"
    "仍未找到用户查询的相关商品数据。"
    "请礼貌告知用户当前无法提供具体商品信息，并给出实用建议：\n"
    "1. 建议用户尝试不同的搜索关键词\n"
    "2. 推荐访问京东、天猫等电商平台直接搜索\n"
    "3. 建议检查产品名称拼写或型号\n"
    "不要编造任何具体的商品价格或参数。"
)


# ---------------------------------------------------------------------------
# RAG Search + LLM Summarize (replaces old search_and_review)
# ---------------------------------------------------------------------------

async def rag_search_products(
    query: str,
    top_k: int = 5,
    try_variants: bool = True,
) -> tuple[list[dict], list[dict]]:
    """Search RAG knowledge base for product information.

    When try_variants=True, also tries expanded query variants if the
    original query returns no results.

    Returns (products, knowledge_docs).
    """
    products: list[dict] = []
    docs: list[dict] = []

    queries_to_try = [query]
    if try_variants:
        expanded = rewrite_query(query)
        # Add top 3 expanded variants (skip the original since it's already first)
        for v in expanded.expanded[1:4]:
            if v not in queries_to_try:
                queries_to_try.append(v)

    for q in queries_to_try:
        try:
            from rag.hybrid_search import hybrid_search
            q_docs = await hybrid_search(q, top_k=top_k)
            for doc in q_docs:
                if doc not in docs:
                    docs.append(doc)
        except Exception:
            pass

        if docs:
            break  # Got results, stop trying variants

    # Extract structured product data from knowledge docs
    for doc in docs[:top_k * 2]:
        content = doc.get("content", "")
        source_name = doc.get("source", doc.get("metadata", {}).get("source", "知识库"))
        score = doc.get("score", 0.0)

        product = _parse_product_from_content(content, source_name, score)
        if product:
            product["source"] = source_name
            product["confidence"] = min(score * 100, 95.0)
            products.append(_enrich_product(product))

    return products, docs


def _parse_product_from_content(
    content: str, source: str, score: float,
) -> dict | None:
    """Try to extract structured product data from knowledge base content."""
    # Parse YAML frontmatter
    if content.startswith("---"):
        try:
            end = content.index("---", 3)
            frontmatter_text = content[3:end]
            fm = {}
            current_key = None
            for line in frontmatter_text.strip().split("\n"):
                line = line.strip()
                if ":" in line and not line.startswith(" "):
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip()
                    current_key = key.strip()
                elif current_key and line.startswith("- "):
                    # List item
                    pass

            name = fm.get("name", "")
            if name:
                price = None
                platform = ""
                # Extract price from platforms list
                platforms_section = frontmatter_text.split("platforms:") if "platforms:" in frontmatter_text else []
                if len(platforms_section) > 1:
                    platforms_text = platforms_section[1].split("\n\n")[0]
                    for line in platforms_text.strip().split("\n"):
                        line = line.strip()
                        if line.startswith("- name:"):
                            platform = line.split("name:")[1].strip()
                        if "price:" in line:
                            try:
                                price = float(line.split("price:")[1].strip())
                            except ValueError:
                                pass
                            if platform and price:
                                break

                return {
                    "name": name,
                    "platform": platform or "多个平台",
                    "price": price or 0,
                    "original_price": None,
                    "rating": float(fm.get("rating", 0)) if fm.get("rating") else None,
                    "specs": fm.get("specs", {}),
                    "source": fm.get("source", source),
                    "url": fm.get("source_url", ""),
                }
        except (ValueError, IndexError):
            pass

    # Fallback: look for price patterns in content
    price_match = re.search(r'[¥￥]\s*(\d[\d,]*)', content)
    name_match = re.search(r'(?:name|名称|产品)[:：]\s*(.+)', content)

    if price_match and name_match:
        return {
            "name": name_match.group(1).strip(),
            "platform": "未知平台",
            "price": float(price_match.group(1).replace(",", "")),
            "source": source,
        }

    return None


async def rag_summarize(
    query: str,
    docs: list[dict],
    intent: str,
    user_id: str = "",
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
    source_type: str = "rag",  # "rag" | "cache" | "live" | "similar" | "template" | "none"
) -> tuple[str, str, float]:
    """Ask LLM to summarize search results. Never fabricates data.

    source_type determines which prompt to use:
      - "rag": RAG knowledge base results
      - "cache": Product cache results
      - "live": Live e-commerce search results
      - "similar": Degraded/similar product results
      - "template": Template (simulated) data
      - "none": No data found at all
    """

    # Build context from search results
    context_parts = []
    for i, doc in enumerate(docs[:8], 1):
        if isinstance(doc, dict):
            # Product dict format (from cache/live search)
            if "name" in doc or "title" in doc:
                name = doc.get("name") or doc.get("title", "未知")
                price = doc.get("price", "")
                platform = doc.get("platform", "未知")
                url = doc.get("url", "")
                conf = doc.get("confidence", "")
                context_parts.append(
                    f"[商品{i}] {name} | {platform} | ¥{price} | 置信度:{conf}%"
                )
            else:
                # RAG doc format
                content = doc.get("content", "")[:500]
                source = doc.get("source", doc.get("metadata", {}).get("source", "未知来源"))
                context_parts.append(f"[文档{i} 来源:{source}]\n{content}")
        elif isinstance(doc, str):
            context_parts.append(doc[:500])

    context = "\n\n---\n\n".join(context_parts) if context_parts else "无相关数据"

    # Select prompt based on source type
    if source_type == "none" or not docs:
        prompt = _NO_DATA_PROMPT
    elif source_type in ("similar", "degraded"):
        prompt = _SIMILAR_PROMPT
    elif source_type in ("cache", "live"):
        prompt = _MULTI_SOURCE_PROMPT
    else:
        prompt = _RAG_SUMMARIZE_PROMPT

    profile = route_query(query, intent)
    content, provider, elapsed = await llm_call(
        system_prompt=prompt,
        user_message=f"用户查询: {query}\n\n检索结果:\n{context}",
        max_tokens=profile.max_tokens,
        temperature=0.3,
        user_id=user_id,
        node_name="rag_summarize",
        stream_callback=stream_callback,
    )
    return content, provider, elapsed


# ---------------------------------------------------------------------------
# Pure-compute nodes
# ---------------------------------------------------------------------------

def compute_price_analysis(products: list[dict]) -> dict:
    if not products:
        return {}
    prices = [
        (p.get("platform", "?"), p.get("price", 0), p.get("original_price", p.get("price", 0)))
        for p in products if p.get("price")
    ]
    if not prices:
        return {}
    sorted_prices = sorted(prices, key=lambda x: x[1])
    best = sorted_prices[0]
    return {
        "best_price": best[1],
        "best_platform": best[0],
        "average_price": round(sum(p[1] for p in prices) / len(prices), 2),
        "price_range": f"¥{sorted_prices[0][1]:,.0f} - ¥{sorted_prices[-1][1]:,.0f}",
        "platforms": [{"name": p[0], "price": p[1], "original": p[2]} for p in prices],
    }


def compute_decision(price_analysis: dict, review_summary: dict, confidence: float = 0) -> dict:
    if not price_analysis:
        return {"recommendation": "no_data", "reason": "未找到足够的商品数据。", "rating": 0, "confidence": 0}

    if confidence < 70:
        return {
            "recommendation": "low_confidence",
            "reason": "当前数据可信度较低，建议访问官方渠道获取准确信息。",
            "rating": 0,
            "confidence": confidence,
        }

    best_price = price_analysis.get("best_price", 0)
    best_platform = price_analysis.get("best_platform", "?")
    verdict = review_summary.get("verdict", "")
    rating = min(3 + len(review_summary.get("pros", [])) * 0.5, 5.0)

    return {
        "recommendation": "consider",
        "best_platform": best_platform,
        "best_price": best_price,
        "rating": round(rating, 1),
        "confidence": round(confidence, 1),
        "reason": f"建议关注{best_platform}的该商品（¥{best_price:,.0f}），推荐参考多个平台后决定。",
    }


def generate_report(
    products: list[dict],
    price_analysis: dict,
    decision: dict,
    user_query: str,
    rag_summary: str = "",
    citation_block: str = "",
    confidence_score: float = 0,
    confidence_warning: str | None = None,
) -> str:
    lines = [f"## {user_query}", ""]

    # Confidence indicator
    lines.append(ConfidenceScorer.format(confidence_score))
    lines.append("")

    if confidence_warning:
        lines.append(f"> ⚠️ {confidence_warning}")
        lines.append("")

    # RAG summary is the primary content
    if rag_summary:
        lines.append(rag_summary)
        lines.append("")

    # Price data (only if from verified sources)
    if price_analysis and products:
        verified_products = [p for p in products if p.get("source") != "simulated"]
        if verified_products:
            lines.append(f"**最佳价格**：{price_analysis.get('best_platform','?')} "
                         f"¥{price_analysis.get('best_price',0):,.0f}")
            lines.append("")

    # Decision
    if decision:
        rec = decision.get("recommendation", "")
        if rec == "no_data":
            lines.append("> ℹ️ 暂无足够数据做出购买建议")
        elif rec == "low_confidence":
            lines.append(f"> ⚠️ {decision.get('reason','')}")
        else:
            lines.append(f"> 💡 {decision.get('reason','')}")

    lines.append("")

    # Show which products used simulated data
    simulated = [p for p in products if p.get("source") == "simulated"]
    if simulated:
        lines.append(f"> ⚠️ 其中{len(simulated)}个商品使用模拟数据，不反映真实市场价格。")
        lines.append("")

    # Citations
    if citation_block:
        lines.append(citation_block)
    else:
        lines.append("---")
        if rag_summary:
            lines.append("📚 数据来源：EVA知识库")
        else:
            lines.append("⚠️ 无可靠数据来源 — 当前知识库未找到相关信息")

    lines.append("")
    lines.append("*EVA Agent | 数据仅供参考，购买前请核实*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline cache
# ---------------------------------------------------------------------------

_result_cache: dict[str, tuple[float, dict]] = {}
_RESULT_CACHE_TTL = 600


def _result_cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Main Pipeline Entry Point (v6 — 5-Layer Search Strategy)
# ---------------------------------------------------------------------------
#
# Flow:
#   Intent → Query Rewrite → Cache Check →
#   Layer 1: RAG (knowledge base) →
#   Layer 2: Product Cache (seed data) →
#   Layer 3: Live Search (e-commerce scraping) →
#   Layer 4: Similar Search (progressive degradation) →
#   Layer 5: Template (simulated, last resort) →
#   not_found (only if ALL layers fail)
# ---------------------------------------------------------------------------

async def run_pipeline(
    user_query: str,
    user_id: str = "",
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
    bypass_cache: bool = False,
) -> dict:
    """v6 Multi-layer shopping pipeline. Returns at least 1 product whenever possible.

    The 5-layer strategy ensures <2% not_found rate:
      1. RAG knowledge base (structured product data)
      2. Product cache (100+ hot products from major platforms)
      3. Live e-commerce search (HTTP scraping + LLM web search)
      4. Similar product search (progressive query degradation)
      5. Template matching (simulated data, clearly marked)
    """
    timer = get_timer()
    timer.start("pipeline")
    tracker = CitationTracker()
    search_layers_used: list[str] = []

    # ── Cache check ──
    rk = _result_cache_key(user_query)
    if not bypass_cache:
        try:
            from app.cache.redis_cache import get_cache
            cache_layer = await get_cache()
            cached = await cache_layer.get(f"eva:query:{rk}")
            if cached and time.time() < cached.get("expiry", 0):
                append_log("INFO", f"pipeline v6 命中缓存 ({user_query[:30]}...)")
                if stream_callback:
                    await stream_callback(cached.get("final_report", ""))
                cached["perf"] = {"cache_hit_ms": timer.elapsed_ms("pipeline")}
                return cached
        except Exception:
            pass

    if not bypass_cache and rk in _result_cache:
        expiry, cached = _result_cache[rk]
        if time.time() < expiry:
            append_log("INFO", f"pipeline v6 命中本地缓存 ({user_query[:30]}...)")
            if stream_callback:
                await stream_callback(cached.get("final_report", ""))
            cached["perf"] = {"cache_hit_ms": round(timer.stop("pipeline"), 1)}
            return cached

    # ── Intent Routing (V2.0: 8-type classifier) (< 1ms) ──
    timer.start("intent")
    from app.agent.intent_router import route_intent, get_route_config, is_shopping_intent
    intent_result = route_intent(user_query)
    intent = intent_result.intent.value  # Keep backwards compat string
    route_cfg = get_route_config(intent_result)
    timer.stop("intent")
    append_log("INFO", f"Intent V2.0: {intent_result.intent.value} "
              f"(conf={intent_result.confidence:.0%}, entities={intent_result.entities_found})")

    # ── Query Rewrite (< 1ms) ──
    expanded_query = rewrite_query(user_query)
    degraded_queries = degrade_query(user_query)

    # ── Entity Extraction (Product NER) (< 1ms) ──
    from app.agent.product_alias_db import resolve_product, get_category_constraint, get_brand_constraint
    entity = resolve_product(user_query)
    entity_category_ok = entity.is_valid and entity.confidence >= 0.4

    # ── Prepare result containers ──
    products: list[dict] = []
    review: dict = {}
    rag_docs: list[dict] = []
    citation_block = ""
    confidence_score = 0.0
    confidence_warning: str | None = None
    verifier = DataVerifier()
    source_type = "none"  # Will be updated as we find data

    if entity_category_ok:
        append_log("INFO", f"Entity detected: brand={entity.brand} product={entity.product} "
                  f"category={entity.category} confidence={entity.confidence:.0%}")

    # ── Non-shopping intents: light LLM chat with intent-specific prompt ──
    if not is_shopping_intent(intent_result):
        from app.agent.intent_router import get_intent_prompt
        intent_prompt = get_intent_prompt(intent_result.intent)

        # For trending/recommend that may benefit from product context
        if intent_result.intent.value in ("trend_analysis", "recommend_products", "shopping_guide"):
            # Try quick hot product lookup for context
            try:
                from app.agent.product_db import get_trending_products
                hot = get_trending_products(top_k=5)
                if hot:
                    context = "热门商品参考：\n" + "\n".join(
                        f"- {h['title']} ({h['brand']}, ¥{h['price_min']}-{h['price_max']})"
                        for h in hot[:5]
                    )
                    user_query = f"{user_query}\n\n{context}"
            except Exception:
                pass

        review_text, _, llm_ms = await llm_call(
            system_prompt=intent_prompt,
            user_message=user_query,
            max_tokens=route_cfg.llm_max_tokens,
            temperature=route_cfg.llm_temperature,
            user_id=user_id,
            node_name=f"intent_{intent_result.intent.value}",
            stream_callback=stream_callback,
        )
        timer.record("llm_chat", llm_ms)
        review = {"verdict": review_text, "pros": [], "cons": []}
        tracker.add(f"AI回复（{intent_result.intent.value}）", source_type="unknown", source_name="LLM")
        confidence_score = 100.0
        source_type = "llm"

    else:
        # ═══════════════════════════════════════════════════════════
        # Shopping intent — 7-Layer Product Search (v6.1)
        # ═══════════════════════════════════════════════════════════

        # ── Layer 0: Hot Products Database (NEW — checked before RAG) ──
        timer.start("layer0_hot")
        try:
            from app.agent.product_db import search_products as search_hot_products
            hot_products = await search_hot_products(
                user_query, top_k=5,
            )
            if hot_products:
                # Normalize hot product fields (title → name)
                normalized = []
                for hp in hot_products:
                    hp["name"] = hp.get("title") or hp.get("name", "未知")
                    hp.setdefault("price", (hp.get("price_min", 0) + hp.get("price_max", 0)) / 2)
                    hp.setdefault("url", hp.get("product_url", ""))
                    normalized.append(hp)
                products = [_enrich_product(p) for p in normalized]
                for p in products:
                    p["source"] = p.get("source", "hot_products")
                    p["popularity_score"] = p.get("popularity_score", 50)
                source_type = "hot_products"
                search_layers_used.append("hot_products")
                review = {"verdict": "数据来自热门商品库", "pros": [], "cons": []}
                append_log("INFO", f"[Layer 0] 热门商品库命中: {len(products)}件商品 "
                          f"(entity={'on' if entity_category_ok else 'off'})")
        except Exception as e:
            append_log("WARN", f"[Layer 0] 热门商品库异常: {str(e)[:80]}")
        timer.stop("layer0_hot")

        # ── Layer 0.5: Trending Search Normalization ──
        if not products:
            try:
                from app.agent.trending_searches import lookup_trending
                trending_match = await lookup_trending(user_query)
                if trending_match and trending_match.get("canonical") != user_query:
                    canonical = trending_match["canonical"]
                    append_log("DEBUG", f"Trending normalization: '{user_query[:30]}' -> '{canonical[:30]}'")
                    # Try cache/hot with canonical query
                    from app.agent.product_db import search_products as search_product_cache
                    cache_from_trend = await search_product_cache(
                        canonical, top_k=5,
                    )
                    if cache_from_trend:
                        products = [_enrich_product(p) for p in cache_from_trend]
                        source_type = "cache"
                        search_layers_used.append("trending_normalize")
                        review = {"verdict": "数据来自热门搜索匹配", "pros": [], "cons": []}
                        append_log("INFO", f"[Layer 0.5] 热门搜索匹配: {len(products)}件商品")
            except Exception:
                pass

        # ── Layer 1: RAG Knowledge Base ──
        timer.start("layer1_rag")
        rag_products, rag_docs = await rag_search_products(user_query, top_k=5, try_variants=True)
        timer.stop("layer1_rag")

        if rag_products:
            products = rag_products
            source_type = "rag"
            search_layers_used.append("rag")
            review = {"verdict": "数据来自知识库", "pros": [], "cons": []}
            append_log("INFO", f"[Layer 1] RAG命中: {len(products)}件商品")

        # ── Layer 2: Product Cache ──
        if not products:
            timer.start("layer2_cache")
            try:
                from app.agent.product_db import search_products as search_product_cache
                # Try original query first, then expanded variants
                cache_products = await search_product_cache(
                    user_query, top_k=5,
                )
                if not cache_products:
                    for variant in expanded_query.expanded[1:4]:
                        cache_products = await search_product_cache(
                            variant, top_k=5,
                        )
                        if cache_products:
                            break

                if cache_products:
                    products = [_enrich_product(p) for p in cache_products]
                    for p in products:
                        p["source"] = p.get("source", "product_cache")
                    source_type = "cache"
                    search_layers_used.append("product_cache")
                    review = {"verdict": "数据来自商品缓存", "pros": [], "cons": []}
                    append_log("INFO", f"[Layer 2] 商品缓存命中: {len(products)}件商品 "
                              f"(entity_filter={'on' if entity_category_ok else 'off'})")
            except Exception as e:
                append_log("WARN", f"[Layer 2] 商品缓存异常: {str(e)[:80]}")
            timer.stop("layer2_cache")

        # ── Layer 3: Live E-commerce Search ──
        if not products:
            timer.start("layer3_live")
            try:
                from app.agent.live_search import live_search_products
                live_products = await live_search_products(
                    user_query, top_k=5, user_id=user_id, timeout=8.0,
                )
                if live_products:
                    # Validate against entity constraints
                    if entity_category_ok:
                        from app.agent.product_validator import validate_and_filter
                        live_products, _ = validate_and_filter(
                            entity, live_products, strict_category=False,  # Live search: lenient
                        )
                    if live_products:
                        products = []
                        for lp in live_products:
                            p = {
                                "name": lp.get("title", user_query),
                                "platform": lp.get("platform", "未知"),
                                "price": lp.get("price", 0.0) if lp.get("price") else 0.0,
                                "url": lp.get("url", ""),
                                "source": "live_search",
                                "confidence": lp.get("confidence", 30.0),
                            }
                            products.append(_enrich_product(p))
                        source_type = "live"
                        search_layers_used.append("live_search")
                        review = {"verdict": "数据来自电商平台实时搜索", "pros": [], "cons": []}
                        append_log("INFO", f"[Layer 3] 实时搜索命中: {len(products)}件商品")
            except Exception as e:
                append_log("WARN", f"[Layer 3] 实时搜索异常: {str(e)[:80]}")
            timer.stop("layer3_live")

        # ── Layer 4: Similar Product Search (progressive degradation) ──
        if not products:
            timer.start("layer4_similar")
            try:
                from app.agent.similar_search import similar_product_search
                similar_products = await similar_product_search(
                    user_query, user_id=user_id, total_timeout=10.0,
                )
                if similar_products:
                    # Validate against entity — keep within same category
                    if entity_category_ok:
                        from app.agent.product_validator import validate_and_filter
                        similar_products, _ = validate_and_filter(
                            entity, similar_products, strict_category=True,
                        )
                    if similar_products:
                        products = [_enrich_product(p) for p in similar_products]
                        for p in products:
                            p["source"] = p.get("source", "similar_search")
                        source_type = "similar"
                        search_layers_used.append("similar_search")
                        best_degradation = min(
                            (p.get("degradation_level", 0) for p in products), default=0
                        )
                        if best_degradation > 0:
                            review = {
                                "verdict": f"未找到精确匹配，以下为相似商品（已放宽搜索条件）",
                                "pros": [],
                                "cons": [],
                                "degradation_note": f"搜索已降级到第{best_degradation}层",
                            }
                        else:
                            review = {"verdict": "找到相关商品", "pros": [], "cons": []}
                        append_log("INFO", f"[Layer 4] 相似搜索命中: {len(products)}件商品 (降级级别:{best_degradation})")
            except Exception as e:
                append_log("WARN", f"[Layer 4] 相似搜索异常: {str(e)[:80]}")
            timer.stop("layer4_similar")

        # ── Layer 5: Template Matching (simulated, last resort) ──
        if not products:
            timer.start("layer5_template")
            template = match_template(user_query)
            if template is not None:
                t_products, t_review = template
                for p in t_products:
                    p["source"] = "simulated"
                    p["confidence"] = 0.0
                t_review["source"] = "simulated"
                products, review = t_products, t_review
                source_type = "simulated"
                search_layers_used.append("template")
                tracker.mark_simulated()
                confidence_warning = "⚠️ 当前使用模拟数据，不反映真实市场价格。建议访问京东/天猫查看最新价格。"
                append_log("WARN", "[Layer 5] 回退到模板（模拟数据），所有真实数据源均无结果")
            timer.stop("layer5_template")

        # ── Layer 6: Entity-aware Search URL Generation (guaranteed fallback) ──
        if not products and entity_category_ok:
            timer.start("layer6_link_fallback")
            # Generate real search URLs for detected brand + product on major platforms
            from urllib.parse import quote as url_quote
            search_terms = entity.product or user_query
            if entity.brand:
                search_terms = f"{entity.brand} {search_terms}"

            platforms_for_entity = {
                "badminton_racket": ["京东", "天猫", "淘宝", "得物", "拼多多", "闲鱼"],
                "badminton_shuttlecock": ["京东", "天猫", "淘宝", "拼多多"],
                "smartphone": ["京东", "天猫", "淘宝", "拼多多", "得物"],
                "graphics_card": ["京东", "天猫", "淘宝", "拼多多"],
                "laptop": ["京东", "天猫", "淘宝", "拼多多"],
                "headphone": ["京东", "天猫", "得物", "拼多多"],
                "shoe": ["得物", "天猫", "京东", "拼多多", "识货"],
                "running_shoe": ["得物", "京东", "天猫", "识货"],
                "gaming_console": ["京东", "天猫", "淘宝", "拼多多"],
            }

            platforms = platforms_for_entity.get(entity.category, ["京东", "天猫", "淘宝", "得物", "拼多多"])
            url_products = []
            for plat in platforms[:4]:
                tmpl = PLATFORM_URLS.get(plat, "")
                if tmpl:
                    url_products.append({
                        "name": f"{search_terms}",
                        "platform": plat,
                        "price": 0.0,
                        "url": tmpl.format(url_quote(search_terms)),
                        "source": "link_fallback",
                        "confidence": 8.0,
                    })

            if url_products:
                products = [_enrich_product(p) for p in url_products]
                source_type = "link_fallback"
                search_layers_used.append("link_fallback")
                review = {"verdict": f"未找到{search_terms}的实时数据，以下为电商平台搜索链接", "pros": [], "cons": []}
                confidence_warning = f"⚠️ 未在缓存中找到 {entity.brand} {entity.product} 的实时价格数据。请点击链接查看最新价格。"
                append_log("INFO", f"[Layer 6] 链接回退: {len(products)}个平台搜索链接")
            timer.stop("layer6_link_fallback")

        # ── Post-search: Re-rank with popularity weighting ──
        if products and len(products) > 1:
            try:
                from app.agent.popularity_scorer import re_rank
                products = re_rank(user_query, products, entity=entity if entity_category_ok else None, top_k=max(5, len(products)))
            except Exception:
                pass

        # ── Post-search: Validate & Compute ──
        if products:
            # Final entity validation (belt-and-suspenders)
            if entity_category_ok and len(products) > 0:
                from app.agent.product_validator import validate_and_filter
                products, validation_report = validate_and_filter(
                    entity, products,
                    strict_brand=(source_type != "link_fallback"),
                    strict_category=True,
                )
                if validation_report.total_rejected > 0:
                    append_log("WARN", f"Post-search validation rejected {validation_report.total_rejected} "
                              f"cross-category results (kept {validation_report.total_accepted})")

            # GUARANTEED RETURN RULE: if we have products after validation, always return them
            if products:
                # Verify data (skip for link_fallback — those are just URLs)
                if source_type != "link_fallback":
                    verifications = await verifier.verify_product_claims(products)
                    confidence_score = DataVerifier.aggregate_confidence(verifications)
                else:
                    confidence_score = 8.0

                # Override confidence for simulated data
                if source_type == "simulated":
                    confidence_score = 0.0
                elif source_type == "similar":
                    confidence_score = min(confidence_score, 60.0)

                # Track sources
                seen_sources: set[str] = set()
                for p in products:
                    src = p.get("source", source_type)
                    if src not in seen_sources:
                        seen_sources.add(src)
                        tracker.add(
                            p.get("name", src)[:60],
                            source_type=src,
                            source_name=p.get("platform", "未知"),
                            confidence=p.get("confidence", confidence_score),
                        )

                append_log(
                    "INFO",
                    f"pipeline v6 完成搜索: {len(products)}件商品 "
                    f"layers={search_layers_used} "
                    f"source={source_type} "
                    f"confidence={confidence_score:.0f}% "
                    f"entity={entity.brand if entity else 'none'}/{entity.category if entity else 'none'}",
                )
            else:
                # All products rejected by validation — this is the true not_found case
                confidence_score = 0.0
                confidence_warning = (
                    "🔴 搜索到的商品均因品牌/分类不匹配被过滤。"
                    "建议尝试不同的搜索关键词，或直接访问京东/天猫搜索。"
                )
                source_type = "none"
                search_layers_used.append("validation_rejected")
                products = []
        else:
            # ── Absolutely no data: ALL layers failed ──
            confidence_score = 0.0
            confidence_warning = (
                "🔴 经过全部搜索层（知识库、商品缓存、电商平台实时搜索、相似商品匹配、模板匹配、链接生成）"
                "均未找到相关商品。建议尝试不同的搜索关键词，或直接访问京东/天猫搜索。"
            )
            source_type = "none"
            tracker.add("所有搜索渠道均未找到商品", source_type="unknown", source_name="无")
            search_layers_used.append("none")
            append_log("WARN", "pipeline v6 所有搜索层均失败 — 返回 not_found")

    # ── LLM Summarization ──
    timer.start("llm_summarize")
    if source_type == "none" and intent in ("shopping", "product_query"):
        # No data — generate helpful not_found message
        review_text, _, llm_ms = await rag_summarize(
            user_query, [], intent, user_id, stream_callback, source_type="none",
        )
        timer.record("llm_summarize", llm_ms)
        review = {"verdict": review_text, "pros": [], "cons": []}
    elif products and intent in ("shopping", "product_query"):
        # Products found — summarize them
        # Build context from products + RAG docs
        summarize_context = list(products[:5])
        if rag_docs:
            summarize_context.extend(rag_docs[:3])
        review_text, _, llm_ms = await rag_summarize(
            user_query, summarize_context, intent, user_id,
            stream_callback, source_type=source_type,
        )
        timer.record("llm_summarize", llm_ms)
        if review_text:
            review = {"verdict": review_text, "pros": [], "cons": []}
    timer.stop("llm_summarize")

    # ── Compute (< 1ms) ──
    timer.start("compute")
    price_analysis = compute_price_analysis(products) if products else {}
    decision = compute_decision(price_analysis, review, confidence_score) if products else {}
    citation_block = tracker.render()

    if not confidence_warning:
        confidence_warning = ConfidenceScorer.get_warning(confidence_score)

    final_report = generate_report(
        products, price_analysis, decision, user_query,
        rag_summary=review.get("verdict", ""),
        citation_block=citation_block,
        confidence_score=confidence_score,
        confidence_warning=confidence_warning,
    )
    timer.stop("compute")

    total_ms = timer.stop("pipeline")

    # ── Build result ──
    # ── Enrich with confidence tiers (V2.0) ──
    if products:
        from app.agent.confidence_tiers import rate_source, get_tier_display
        for p in products:
            src = p.get("source", source_type)
            tier, tier_label = rate_source(src)
            p["tier"] = tier.value
            p["tier_label"] = tier_label
            p["tier_display"] = get_tier_display(src, p.get("confidence", 50))

    # ── Product Graph suggestions (V2.0) ──
    graph_suggestions = []
    if entity and entity.product:
        try:
            from app.agent.product_graph import find_node_by_model, suggest_similar
            graph_node = find_node_by_model(entity.product)
            if graph_node:
                graph_suggestions = suggest_similar(graph_node.id, top_k=3)
        except Exception:
            pass

    result = {
        "intent": intent,
        "intent_type": intent_result.intent.value,
        "intent_confidence": intent_result.confidence,
        "search_results": products,
        "price_analysis": price_analysis,
        "review_summary": review,
        "decision": decision,
        "final_report": final_report,
        "perf": timer.report(),
        "confidence": confidence_score,
        "confidence_warning": confidence_warning,
        "citation": tracker.render_short(),
        "data_source": source_type,
        "search_layers": search_layers_used,
        "total_products_found": len(products),
        "entity": entity.to_dict() if entity else {},
        "graph_suggestions": graph_suggestions,
        "fast_mode": route_cfg.fast_mode,
    }

    # ── Cache result ──
    _result_cache[rk] = (time.time() + _RESULT_CACHE_TTL, result)
    try:
        from app.cache.redis_cache import get_cache
        cache_layer = await get_cache()
        await cache_layer.set(
            f"eva:query:{rk}",
            {**result, "expiry": time.time() + _RESULT_CACHE_TTL},
            ttl=_RESULT_CACHE_TTL,
        )
    except Exception:
        pass

    append_log(
        "SUCCESS",
        f"pipeline v6 完成 ({total_ms:.0f}ms) intent={intent} "
        f"products={len(products)} layers={search_layers_used} "
        f"confidence={confidence_score:.0f}% source={source_type}",
    )

    return result
