"""Tool Executor — Database, API, and computation execution.

Handles Step "Tool" of the Hybrid AI decision flow:
  - Database queries (product DB, user data, analytics)
  - API calls (price checks, platform status)
  - Numerical computation (price comparison, statistics)
  - Structured data processing

Usage:
    from app.hybrid.tool_executor import execute_tool_query

    result = await execute_tool_query("对比iPhone价格", user_id="...")
"""

import json
import time
from typing import Any

from app.hybrid.types import SourceEvidence, SourceResult, SourceType
from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Tool dispatch — maps query intent → tool functions
# ═══════════════════════════════════════════════════════════════════════

async def _query_product_db(query: str, top_k: int = 5) -> list[dict]:
    """Query the product database for structured product data."""
    try:
        from app.models.product import Product
        from app.core.database import async_session
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(Product).where(Product.name.contains(query)).limit(top_k)
            )
            products = result.scalars().all()
            return [
                {
                    "name": p.name,
                    "platform": p.platform,
                    "price": float(p.price) if p.price else 0,
                    "rating": float(p.rating) if p.rating else None,
                    "source": "product_db",
                    "url": getattr(p, 'url', ''),
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in products
            ]
    except Exception as e:
        append_log("WARN", f"Product DB query failed: {str(e)[:80]}")
        return []


async def _query_favorites(user_id: str, limit: int = 10) -> list[dict]:
    """Query the user's favorite products."""
    try:
        from app.models.favorite import Favorite
        from app.core.database import async_session
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(Favorite)
                .where(Favorite.user_id == user_id)
                .order_by(Favorite.created_at.desc())
                .limit(limit)
            )
            favs = result.scalars().all()
            return [
                {
                    "name": f.product_name,
                    "platform": f.product_platform,
                    "price": float(f.product_price) if f.product_price else 0,
                    "url": f.product_url,
                    "source": "favorites_db",
                }
                for f in favs
            ]
    except Exception:
        return []


async def _query_reports(user_id: str, limit: int = 5) -> list[dict]:
    """Query the user's previous analysis reports."""
    try:
        from app.models.report import Report
        from app.core.database import async_session
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(Report)
                .where(Report.user_id == user_id)
                .order_by(Report.created_at.desc())
                .limit(limit)
            )
            reports = result.scalars().all()
            return [
                {
                    "title": r.title,
                    "summary": r.summary,
                    "type": r.type,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "source": "reports_db",
                }
                for r in reports
            ]
    except Exception:
        return []


async def _compute_price_analysis(products: list[dict]) -> dict:
    """Pure computation: price statistics from product list."""
    if not products:
        return {"error": "无商品数据"}

    prices = [
        (p.get("platform", "?"), p.get("price", 0))
        for p in products
        if p.get("price") and float(p.get("price", 0)) > 0
    ]

    if not prices:
        return {"error": "无有效价格数据"}

    prices_sorted = sorted(prices, key=lambda x: x[1])
    avg = sum(p[1] for p in prices) / len(prices)

    return {
        "best_platform": prices_sorted[0][0],
        "best_price": prices_sorted[0][1],
        "highest_price": prices_sorted[-1][1],
        "average_price": round(avg, 2),
        "price_range": f"¥{prices_sorted[0][1]:,.0f} - ¥{prices_sorted[-1][1]:,.0f}",
        "platform_count": len(set(p[0] for p in prices)),
        "total_compared": len(prices),
    }


# ═══════════════════════════════════════════════════════════════════════
# Tool dispatch logic
# ═══════════════════════════════════════════════════════════════════════

_PRICE_PATTERNS = ["价格", "多少钱", "比价", "报价", "最低价", "price"]
_COMPARE_PATTERNS = ["对比", "比较", "哪个便宜", "vs", "compare"]
_DATA_PATTERNS = ["数据", "统计", "查询", "记录", "历史", "我的", "收藏"]


def _infer_tool_type(query: str) -> str:
    """Infer which tool type to use from the query."""
    q = query.lower()
    if any(p in q for p in _PRICE_PATTERNS):
        return "price_analysis"
    if any(p in q for p in _COMPARE_PATTERNS):
        return "comparison"
    if any(p in q for p in _DATA_PATTERNS):
        return "data_query"
    return "general"


async def execute_tool_query(
    query: str,
    user_id: str = "",
    products: list[dict] | None = None,
) -> SourceResult:
    """Execute tool-based query (DB, API, computation).

    Args:
        query: User's query text
        user_id: Current user ID
        products: Optional pre-fetched product list for computation

    Returns:
        SourceResult with evidence from tool execution.
    """
    t0 = time.perf_counter()
    tool_type = _infer_tool_type(query)
    evidence_list: list[SourceEvidence] = []

    try:
        if tool_type == "price_analysis":
            # If we have products, do pure computation
            if products:
                analysis = await _compute_price_analysis(products)
                evidence_list.append(SourceEvidence(
                    source=SourceType.TOOL,
                    content=json.dumps(analysis, ensure_ascii=False, indent=2),
                    relevance_score=0.9,
                    authority="api",
                ))
            else:
                # Otherwise query DB
                db_products = await _query_product_db(query)
                if db_products:
                    analysis = await _compute_price_analysis(db_products)
                    evidence_list.append(SourceEvidence(
                        source=SourceType.TOOL,
                        content=json.dumps(analysis, ensure_ascii=False, indent=2),
                        relevance_score=0.8,
                        authority="database",
                    ))

        elif tool_type == "comparison":
            # Query DB for comparison
            if products:
                analysis = await _compute_price_analysis(products)
                evidence_list.append(SourceEvidence(
                    source=SourceType.TOOL,
                    content=json.dumps(analysis, ensure_ascii=False, indent=2),
                    relevance_score=0.85,
                    authority="api",
                ))

        elif tool_type == "data_query":
            # Query user data (favorites, reports)
            if user_id:
                favs = await _query_favorites(user_id)
                if favs:
                    evidence_list.append(SourceEvidence(
                        source=SourceType.TOOL,
                        content=f"用户收藏商品 ({len(favs)}个):\n" +
                                "\n".join(f"- {f['name']} @ ¥{f['price']}" for f in favs[:5]),
                        relevance_score=0.6,
                        authority="database",
                    ))

                reports = await _query_reports(user_id)
                if reports:
                    evidence_list.append(SourceEvidence(
                        source=SourceType.TOOL,
                        content=f"历史分析报告 ({len(reports)}个):\n" +
                                "\n".join(f"- {r['title']}" for r in reports[:5]),
                        relevance_score=0.6,
                        authority="database",
                    ))

        # Always try product DB as general fallback
        if not evidence_list:
            db_products = await _query_product_db(query)
            if db_products:
                evidence_list.append(SourceEvidence(
                    source=SourceType.TOOL,
                    content=f"数据库中找到{len(db_products)}个相关商品:\n" +
                            "\n".join(
                                f"- {p['name']} ({p['platform']}) ¥{p['price']}"
                                for p in db_products[:5]
                            ),
                    relevance_score=0.5,
                    authority="database",
                ))

    except Exception as e:
        append_log("ERROR", f"Tool execution failed: {str(e)[:80]}")
        return SourceResult(
            source=SourceType.TOOL,
            success=False,
            error=str(e)[:100],
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    latency_ms = (time.perf_counter() - t0) * 1000

    return SourceResult(
        source=SourceType.TOOL,
        success=len(evidence_list) > 0,
        evidence=evidence_list,
        latency_ms=latency_ms,
    )


def compute_confidence_breakdown(
    sources_count: int,
    has_web: bool = False,
    has_rag: bool = False,
    has_tool: bool = False,
    data_freshness_days: int | None = None,
    authority: str = "unknown",
) -> dict:
    """Compute confidence breakdown from source combination.

    Returns dict with sources_score, freshness_score, relevance_score,
    authority_score, and total.
    """
    # Sources score: more sources = more confidence
    if sources_count >= 3:
        sources_score = 35.0
    elif sources_count == 2:
        sources_score = 25.0
    elif sources_count == 1:
        sources_score = 15.0
    else:
        sources_score = 5.0

    # Freshness: web > recent db > old data
    if has_web:
        freshness_score = 30.0
    elif data_freshness_days is not None and data_freshness_days <= 30:
        freshness_score = 25.0
    elif data_freshness_days is not None and data_freshness_days <= 90:
        freshness_score = 18.0
    else:
        freshness_score = 8.0

    # Relevance: tool/rag data is structured → higher relevance
    if has_tool and has_rag:
        relevance_score = 18.0
    elif has_tool:
        relevance_score = 15.0
    elif has_rag:
        relevance_score = 12.0
    else:
        relevance_score = 8.0

    # Authority
    authority_map = {
        "official": 10.0, "api": 9.0, "database": 8.0,
        "rag": 6.0, "community": 3.0, "unknown": 1.0,
    }
    authority_score = authority_map.get(authority, 1.0)

    total = round(sources_score + freshness_score + relevance_score + authority_score, 1)

    return {
        "sources_score": sources_score,
        "freshness_score": freshness_score,
        "relevance_score": relevance_score,
        "authority_score": authority_score,
        "total": min(total, 100.0),
    }
