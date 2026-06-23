"""Database Query Tool — 结构化数据查询

数据源: MySQL / SQLite
支持: 用户信息、订单、收藏、商品、报告查询
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="db_query",
    description="查询数据库中的结构化数据：用户信息、订单记录、收藏商品、历史报告。不直接查询用户密码等敏感信息。",
    category="data",
    parameters={
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": ["user_info", "orders", "favorites", "reports", "products", "chat_history"],
                "description": "查询类型",
            },
            "user_id": {
                "type": "string",
                "description": "用户ID（查询用户相关数据时必需）",
            },
            "limit": {
                "type": "integer",
                "description": "返回记录数，默认10",
                "default": 10,
            },
        },
        "required": ["query_type"],
    },
)
async def query_database(
    query_type: str,
    user_id: str = "",
    limit: int = 10,
) -> ToolResult:
    """数据库查询"""
    try:
        from app.core.database import async_session

        data = []

        async with async_session() as db:
            if query_type == "favorites" and user_id:
                from sqlalchemy import select
                from app.models.favorite import Favorite
                stmt = (
                    select(Favorite)
                    .where(Favorite.user_id == int(user_id))
                    .order_by(Favorite.created_at.desc())
                    .limit(limit)
                )
                result = await db.execute(stmt)
                favorites = result.scalars().all()
                data = [
                    {
                        "id": f.id,
                        "product_name": f.product_name or "",
                        "platform": f.platform or "",
                        "price": f.price or 0,
                        "created_at": f.created_at.isoformat() if f.created_at else "",
                    }
                    for f in favorites
                ]

            elif query_type == "reports" and user_id:
                from sqlalchemy import select
                from app.models.report import Report
                stmt = (
                    select(Report)
                    .where(Report.user_id == int(user_id))
                    .order_by(Report.created_at.desc())
                    .limit(limit)
                )
                result = await db.execute(stmt)
                reports = result.scalars().all()
                data = [
                    {
                        "id": r.id,
                        "title": r.title or "",
                        "summary": (r.content or "")[:200],
                        "created_at": r.created_at.isoformat() if r.created_at else "",
                    }
                    for r in reports
                ]

            elif query_type == "products":
                from sqlalchemy import select, text
                stmt = text(
                    "SELECT id, name, brand, category, platform, price_min, price_max "
                    "FROM products ORDER BY created_at DESC LIMIT :limit"
                )
                result = await db.execute(stmt, {"limit": limit})
                rows = result.fetchall()
                data = [
                    {
                        "id": row[0],
                        "name": row[1] or "",
                        "brand": row[2] or "",
                        "category": row[3] or "",
                        "platform": row[4] or "",
                        "price_min": row[5] or 0,
                        "price_max": row[6] or 0,
                    }
                    for row in rows
                ]

            elif query_type == "user_info" and user_id:
                from sqlalchemy import select
                from app.models.user import User
                stmt = select(User).where(User.id == int(user_id))
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()
                if user:
                    data = [{
                        "id": user.id,
                        "email": user.email,
                        "display_name": getattr(user, "display_name", ""),
                        "role": getattr(user, "role", "user"),
                        "created_at": user.created_at.isoformat() if user.created_at else "",
                    }]

            else:
                return ToolResult.failed(
                    tool="db_query",
                    error=f"不支持的查询类型: {query_type}",
                )

        if not data:
            return ToolResult.partial(
                tool="db_query",
                data=[],
                confidence=0.5,
                source="mysql",
                error=f"未找到 {query_type} 相关数据",
            )

        return ToolResult.success(
            tool="db_query",
            data=data,
            confidence=0.95,
            source="mysql",
            query_type=query_type,
            total=len(data),
        )

    except Exception as e:
        return ToolResult.failed(
            tool="db_query",
            error=f"数据库查询失败: {str(e)[:200]}",
        )
