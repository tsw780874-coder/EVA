"""RAG-First Shopping Pipeline — no fabricated data.

v5 anti-hallucination architecture:
  User → Intent → RAG Search → Data Verification → LLM summarizes → Citations → Report

Key principles:
  1. Never ask LLM to generate product data. Products come from RAG/DB only.
  2. Every factual claim is verified before presentation.
  3. If no real data is found, say "未找到可靠信息" — never guess.
  4. All responses include citations and confidence scores.
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
# Anti-hallucination prompts (v5 — no data fabrication)
# ---------------------------------------------------------------------------

_QUICK_CHAT_PROMPT = (
    "你是一个友好的AI购物助手。如果问题涉及具体商品信息（价格、参数、评价），"
    "请基于提供的上下文回答，不要凭记忆编造数据。"
    "如果上下文中没有相关信息，请诚实告知用户：'未找到可靠信息，建议访问官方渠道确认。'"
    "用中文简洁回复，2-3句话。"
)

# RAG-context prompt: LLM only SUMMARIZES, never generates product data
_RAG_SUMMARIZE_PROMPT = (
    "你是电商购物专家。请基于以下检索到的知识库内容，回答用户问题。\n"
    "规则：\n"
    "1. 只使用下方提供的知识库内容，不要凭自己的记忆补充\n"
    "2. 如果知识库内容不足以回答，明确说'当前知识库未找到相关信息'\n"
    "3. 在回答中注明信息来源\n"
    "4. 用中文回复，结构清晰"
)

# Fallback: no RAG data found
_NO_DATA_PROMPT = (
    "你是电商购物专家。知识库中未找到用户查询的相关商品数据。"
    "请礼貌告知用户当前无法提供具体商品信息，并给出实用建议（如：去哪查官方价格、"
    "如何比价等）。不要编造任何具体的商品价格或参数。"
)


# ---------------------------------------------------------------------------
# RAG Search + LLM Summarize (replaces old search_and_review)
# ---------------------------------------------------------------------------

async def rag_search_products(
    query: str,
    top_k: int = 5,
) -> tuple[list[dict], list[dict]]:
    """Search RAG knowledge base for product information.

    Returns (products, knowledge_docs).
    Products are extracted from structured knowledge base entries.
    knowledge_docs contains raw RAG results for LLM context.
    """
    products: list[dict] = []
    docs: list[dict] = []

    try:
        from rag.hybrid_search import hybrid_search
        docs = await hybrid_search(query, top_k=top_k)
    except Exception:
        pass

    # Extract structured product data from knowledge docs
    for doc in docs:
        content = doc.get("content", "")
        source_name = doc.get("source", doc.get("metadata", {}).get("source", "知识库"))
        score = doc.get("score", 0.0)

        # Parse product info from knowledge content
        # Look for YAML frontmatter or structured data patterns
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
) -> tuple[str, str, float]:
    """Ask LLM to summarize RAG results. Never fabricates data."""

    # Build context from RAG results
    context_parts = []
    for i, doc in enumerate(docs[:5], 1):
        content = doc.get("content", "")[:500]
        source = doc.get("source", doc.get("metadata", {}).get("source", "知识库"))
        context_parts.append(f"[文档{i} 来源:{source}]\n{content}")

    context = "\n\n---\n\n".join(context_parts) if context_parts else "无相关文档"

    if not docs:
        # No RAG data — use no-data prompt
        content, provider, elapsed = await llm_call(
            system_prompt=_NO_DATA_PROMPT,
            user_message=f"用户查询: {query}",
            max_tokens=300,
            temperature=0.5,
            user_id=user_id,
            node_name="rag_summarize",
            stream_callback=stream_callback,
        )
        return content, provider, elapsed

    # RAG data available — summarize it
    profile = route_query(query, intent)
    content, provider, elapsed = await llm_call(
        system_prompt=_RAG_SUMMARIZE_PROMPT,
        user_message=f"用户查询: {query}\n\n知识库检索结果:\n{context}",
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
# Main Pipeline Entry Point (RAG-First v5)
# ---------------------------------------------------------------------------

async def run_pipeline(
    user_query: str,
    user_id: str = "",
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
    bypass_cache: bool = False,
) -> dict:
    """RAG-First shopping pipeline. No fabricated data.

    Flow:
      Intent → RAG Search → Verify → LLM Summarize → Compute → Report
    """
    timer = get_timer()
    timer.start("pipeline")
    tracker = CitationTracker()

    # ── Cache check ──
    rk = _result_cache_key(user_query)
    if not bypass_cache:
        try:
            from app.cache.redis_cache import get_cache
            cache_layer = await get_cache()
            cached = await cache_layer.get(f"eva:query:{rk}")
            if cached and time.time() < cached.get("expiry", 0):
                append_log("INFO", f"pipeline 命中缓存 ({user_query[:30]}...)")
                if stream_callback:
                    await stream_callback(cached.get("final_report", ""))
                cached["perf"] = {"cache_hit_ms": timer.elapsed_ms("pipeline")}
                return cached
        except Exception:
            pass

    if not bypass_cache and rk in _result_cache:
        expiry, cached = _result_cache[rk]
        if time.time() < expiry:
            append_log("INFO", f"pipeline 命中缓存 ({user_query[:30]}...)")
            if stream_callback:
                await stream_callback(cached.get("final_report", ""))
            cached["perf"] = {"cache_hit_ms": round(timer.stop("pipeline"), 1)}
            return cached

    # ── Intent (<1ms) ──
    timer.start("intent")
    intent = classify_intent(user_query)
    timer.stop("intent")

    # ── RAG Search (v5: primary data source) ──
    products: list[dict] = []
    review: dict = {}
    rag_docs: list[dict] = []
    citation_block = ""
    confidence_score = 0.0
    confidence_warning: str | None = None
    verifier = DataVerifier()

    timer.start("rag_search")

    if intent in ("shopping", "product_query"):
        # 1st — RAG search for REAL data (v5: trustworthiness first)
        rag_products, rag_docs = await rag_search_products(user_query, top_k=5)
        timer.stop("rag_search")
        timer.record("rag_search", (time.perf_counter() - timer._starts.get("rag_search", time.perf_counter())) * 1000)

        if rag_products:
            # Got real data from RAG
            products = rag_products
            review = {"verdict": "数据来自知识库", "pros": [], "cons": []}

            # Verify data
            verifications = await verifier.verify_product_claims(products)
            confidence_score = DataVerifier.aggregate_confidence(verifications)

            # Track sources
            seen_sources = set()
            for v in verifications:
                for s in v.sources:
                    if s not in seen_sources:
                        seen_sources.add(s)
                        tracker.add(s, source_type="rag" if "知识库" in s else "database",
                                   source_name=s, confidence=v.overall_confidence)

            append_log("INFO", f"pipeline RAG命中 ({len(products)}件商品, confidence={confidence_score:.0f}%)")

        elif rag_docs:
            # RAG returned docs but no structured products — summarize
            review_text, _, llm_ms = await rag_summarize(
                user_query, rag_docs, intent, user_id, stream_callback,
            )
            timer.record("llm_summarize", llm_ms)
            review = {"verdict": review_text or "未找到可靠信息", "pros": [], "cons": []}
            confidence_score = 50.0  # Partial: has context but no structured data
            confidence_warning = "知识库中有相关信息但未索引为结构化商品数据。"
            tracker.add("知识库检索结果", source_type="rag", source_name="知识库",
                       confidence=50.0)
            append_log("INFO", "pipeline RAG文档命中，LLM总结")

        else:
            # 2nd — Ultimate fallback: template match (marked simulated)
            template = match_template(user_query)
            if template is not None:
                t_products, t_review = template
                for p in t_products:
                    p["source"] = "simulated"
                    p["confidence"] = 0.0
                t_review["source"] = "simulated"
                products, review = t_products, t_review
                tracker.mark_simulated()
                confidence_score = 0.0
                confidence_warning = "⚠️ 当前使用模拟数据，不反映真实市场价格。建议访问京东/天猫查看最新价格。"
                timer.record("template_fallback", 0.0)
                append_log("WARN", "pipeline 回退到模板（模拟数据），RAG无结果")
            else:
                # 3rd — No data at all
                confidence_score = 0.0
                confidence_warning = ConfidenceScorer.get_warning(0.0)
                tracker.add("未找到任何商品数据", source_type="unknown", source_name="无")
                append_log("WARN", "pipeline 无数据（RAG空+无模板匹配）")
    else:
        # General chat — light LLM
        timer.stop("rag_search")
        review_text, _, llm_ms = await rag_summarize(
            user_query, [], intent, user_id, stream_callback,
        )
        timer.record("llm_chat", llm_ms)
        review = {"verdict": review_text, "pros": [], "cons": []}
        tracker.add("AI对话回复（非商品查询）", source_type="unknown", source_name="LLM")
        confidence_score = 100.0  # General chat: high confidence (no factual claims to verify)

    # ── Compute (<1ms) ──
    timer.start("compute")
    price_analysis = compute_price_analysis(products) if products else {}
    decision = compute_decision(price_analysis, review, confidence_score) if products else {}
    citation_block = tracker.render()
    final_report = generate_report(
        products, price_analysis, decision, user_query,
        rag_summary=review.get("verdict", ""),
        citation_block=citation_block,
        confidence_score=confidence_score,
        confidence_warning=confidence_warning,
    )
    timer.stop("compute")

    total_ms = timer.stop("pipeline")

    result = {
        "intent": intent,
        "search_results": products,
        "price_analysis": price_analysis,
        "review_summary": review,
        "decision": decision,
        "final_report": final_report,
        "perf": timer.report(),
        "confidence": confidence_score,
        "confidence_warning": confidence_warning,
        "citation": tracker.render_short(),
        "data_source": "rag" if rag_docs else ("simulated" if tracker._has_simulated_data else ("llm" if intent not in ("shopping", "product_query") else "none")),
    }
    # Ensure general chat path also has trust metadata
    if "confidence" not in result:
        result["confidence"] = confidence_score
    if "data_source" not in result:
        result["data_source"] = "llm"

    # ── Cache ──
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
        f"pipeline v5 完成 ({total_ms:.0f}ms) intent={intent} "
        f"products={len(products)} confidence={confidence_score:.0f}% "
        f"source={result['data_source']}",
    )

    return result
