from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.api.deps import get_db, require_user
from app.models.user import User
from app.models.product import Product
from app.models.agent_run import AgentRun

router = APIRouter(prefix="/products", tags=["products"])


def _build_platform_comparison(same_name_products: list[Product], current: Product) -> list[dict]:
    """构建跨平台价格对比（仅使用数据库真实数据）"""
    seen_platforms = {current.platform}
    comparison = [{
        "name": current.platform,
        "price": current.price or 0,
    }]

    for p in same_name_products:
        if p.platform not in seen_platforms:
            seen_platforms.add(p.platform)
            comparison.append({
                "name": p.platform,
                "price": p.price or 0,
            })

    return comparison


@router.get("/search")
async def search_products(
    q: str = Query(default="", description="搜索关键词"),
    platform: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    query = select(Product)
    if q:
        query = query.where(Product.name.contains(q))
    if platform:
        query = query.where(Product.platform == platform)
    query = query.limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()
    return [{"id": p.id, "name": p.name, "platform": p.platform, "price": p.price,
             "original_price": p.original_price, "url": p.url, "image_url": p.image_url,
             "rating": p.rating, "review_count": p.review_count} for p in products]


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 查找同款商品跨平台对比
    same_name_result = await db.execute(
        select(Product).where(
            Product.name == product.name,
            Product.id != product.id,
        ).limit(5)
    )
    same_name_products = same_name_result.scalars().all()

    price_trend = await _get_real_price_history(product, db)
    platform_comparison = _build_platform_comparison(same_name_products, product)
    dimensions = _build_dimensions(product, same_name_products)

    return {
        "id": product.id, "name": product.name, "platform": product.platform,
        "price": product.price, "original_price": product.original_price,
        "url": product.url, "image_url": product.image_url,
        "description": product.description, "specs": product.specs,
        "rating": product.rating, "review_count": product.review_count,
        "updated_at": product.updated_at.isoformat(),
        "price_trend": price_trend,
        "platform_comparison": platform_comparison,
        "dimensions": dimensions,
        "ai_analysis": None,
        "suggested_price": product.price,
        "suggested_platform": product.platform,
    }


async def _get_real_price_history(product: Product, db: AsyncSession) -> list[dict]:
    """从 AgentRun 记录中提取真实价格历史"""
    from datetime import datetime, timezone, timedelta

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(AgentRun)
        .where(
            AgentRun.agent_type == "search_agent",
            AgentRun.status == "success",
            AgentRun.created_at >= seven_days_ago,
        )
        .order_by(AgentRun.created_at.asc())
        .limit(50)
    )
    runs = result.scalars().all()

    trend = []
    for run in runs:
        if run.output_data and isinstance(run.output_data, dict):
            results = run.output_data.get("search_results", [])
            for r in results:
                if isinstance(r, dict) and r.get("name") == product.name:
                    trend.append({
                        "day": run.created_at.strftime("%m-%d"),
                        "price": r.get("price", product.price),
                    })

    if not trend:
        return []

    return trend[-7:]


def _build_dimensions(product: Product, same_name_products: list[Product]) -> list[dict]:
    """构建维度评分（仅包含可计算指标）"""
    dimensions = []

    all_prices = [p.price for p in same_name_products if p.price] + ([product.price] if product.price else [])
    if len(all_prices) >= 2 and min(all_prices) > 0:
        price_score = round((min(all_prices) / max(all_prices)) * 100)
        dimensions.append({"label": "价格优势", "score": min(price_score, 100)})

    return dimensions
