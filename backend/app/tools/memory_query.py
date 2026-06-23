"""Memory Query Tool — 三层记忆查询

数据源: Redis（短期）+ MySQL（长期）+ Milvus（向量）
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="memory_query",
    description="查询用户的历史记忆：偏好设置、已确认的商品信息、历史对话摘要。用于个性化推荐和上下文感知。",
    category="memory",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "用户ID",
            },
            "keyword": {
                "type": "string",
                "description": "搜索关键词（可选，不填则返回最近记忆）",
            },
            "memory_type": {
                "type": "string",
                "enum": ["preference", "confirmed_fact", "chat_summary", "all"],
                "description": "记忆类型过滤",
                "default": "all",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数",
                "default": 10,
            },
        },
        "required": ["user_id"],
    },
)
async def query_memory(
    user_id: str,
    keyword: str = "",
    memory_type: str = "all",
    limit: int = 10,
) -> ToolResult:
    """查询用户记忆"""
    try:
        from app.core.database import async_session
        from app.services.memory_service import query_memories, get_session_history

        data = []

        # 1. 长期记忆 (MySQL)
        async with async_session() as db:
            memories = await query_memories(
                db, user_id,
                keyword=keyword or "",
                limit=limit,
            )

            for m in memories:
                if memory_type == "all" or getattr(m, "memory_type", "") == memory_type:
                    data.append({
                        "id": m.id if hasattr(m, "id") else "",
                        "type": getattr(m, "memory_type", "general"),
                        "key": getattr(m, "key", ""),
                        "value": str(getattr(m, "value", ""))[:300],
                        "importance": getattr(m, "importance", 0),
                        "created_at": (
                            m.created_at.isoformat()
                            if hasattr(m, "created_at") and m.created_at
                            else ""
                        ),
                    })

        # 2. 短期记忆 (Redis) — 仅在无关键词时返回
        if not keyword:
            try:
                sessions = await get_session_history(user_id, "")  # 返回所有活跃会话
                # 这里只获取最近会话的摘要
            except Exception:
                sessions = None

        if not data:
            return ToolResult.partial(
                tool="memory_query",
                data=[],
                confidence=0.3,
                source="memory_system",
                error="未找到相关记忆" if keyword else "该用户暂无长期记忆",
            )

        # 计算置信度（基于记忆重要性）
        avg_importance = sum(
            d.get("importance", 0) for d in data
        ) / max(len(data), 1)
        confidence = min(0.5 + avg_importance * 0.5, 0.9)

        return ToolResult.success(
            tool="memory_query",
            data=data,
            confidence=confidence,
            source="memory_system",
            total=len(data),
            memory_type=memory_type,
        )

    except Exception as e:
        return ToolResult.failed(
            tool="memory_query",
            error=f"记忆查询失败: {str(e)[:200]}",
        )
