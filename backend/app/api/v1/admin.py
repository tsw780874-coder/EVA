import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, insert, text
from app.api.deps import get_db, require_admin
from app.models.user import User
from app.models.agent_run import AgentRun
from app.models.product import Product
from app.models.report import Report
from app.models.favorite import Favorite
from app.config import get_settings
from app.core.llm import get_available_models, verify_model, get_model_config

router = APIRouter(prefix="/admin", tags=["admin"])

# 请求追踪
_request_counter: dict[str, int] = {}
_latency_buffer: list[float] = []


def track_request(model_key: str, latency_ms: float):
    _request_counter[model_key] = _request_counter.get(model_key, 0) + 1
    _latency_buffer.append(latency_ms)
    if len(_latency_buffer) > 500:
        _latency_buffer.pop(0)


def get_request_stats():
    total = sum(_request_counter.values())
    avg_latency = round(sum(_latency_buffer) / len(_latency_buffer), 1) if _latency_buffer else 0
    return total, avg_latency


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    users_count = (await db.execute(select(func.count(User.id)))).scalar() or 0
    agents_count = (await db.execute(select(func.count(AgentRun.id)))).scalar() or 0
    products_count = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    reports_count = (await db.execute(select(func.count(Report.id)))).scalar() or 0
    avg_duration_result = await db.execute(select(func.avg(AgentRun.duration_ms)))
    avg_duration = avg_duration_result.scalar() or 0

    return {
        "users": users_count,
        "agent_runs": agents_count,
        "products": products_count,
        "reports": reports_count,
        "avg_agent_duration_ms": round(avg_duration, 1),
    }


@router.get("/agents")
async def get_agent_runs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(
        select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [
        {
            "id": r.id, "user_id": r.user_id, "agent_type": r.agent_type,
            "status": r.status, "duration_ms": r.duration_ms,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/models")
async def get_model_status(
    _admin: User = Depends(require_admin),
):
    models = get_available_models()
    total_requests, avg_latency = get_request_stats()
    return {
        "models": models,
        "total_requests_today": total_requests,
        "avg_latency_ms": avg_latency,
    }


@router.get("/models/verify")
async def verify_models(
    _admin: User = Depends(require_admin),
):
    results = {}
    for model in get_available_models():
        results[model["key"]] = await verify_model(model["key"])
    return {"verified": results}


@router.get("/rag")
async def get_rag_status(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    # 统计实际知识库数据
    report_count = (await db.execute(select(func.count(Report.id)))).scalar() or 0
    product_count = (await db.execute(select(func.count(Product.id)))).scalar() or 0
    doc_count = report_count + product_count

    # 估算 chunks: 每个报告 ~3 段落，每个商品 ~2 段落
    total_chunks = report_count * 3 + product_count * 2

    # 获取最近同步时间（最近报告生成时间）
    last_report_result = await db.execute(
        select(Report.created_at).order_by(Report.created_at.desc()).limit(1)
    )
    last_sync = last_report_result.scalar_one_or_none()

    return {
        "collection": "eva_knowledge",
        "document_count": doc_count,
        "total_chunks": total_chunks,
        "last_sync": last_sync.isoformat() if last_sync else None,
        "status": "active" if doc_count > 0 else "idle",
    }


@router.get("/mcp")
async def get_mcp_status(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    # Try live MCP server stats first
    try:
        from mcp_server.server import get_mcp_stats
        return get_mcp_stats()
    except (ImportError, Exception):
        pass

    # Fallback to agent_runs indirect monitoring
    agent_types = {
        "search_products": "搜索商品",
        "compare_price": "价格对比",
        "analyze_reviews": "评论分析",
        "generate_report": "报告生成",
        "save_memory": "保存记忆",
        "query_memory": "查询记忆",
        "web_search": "网页搜索",
        "rag_search": "RAG搜索",
    }

    connectors = []
    for tool_key, tool_label in agent_types.items():
        # 查询该 agent 最近一次成功运行
        result = await db.execute(
            select(AgentRun)
            .where(AgentRun.agent_type == tool_key, AgentRun.status == "success")
            .order_by(AgentRun.created_at.desc())
            .limit(1)
        )
        last_run = result.scalar_one_or_none()

        # 平均延迟
        avg_result = await db.execute(
            select(func.avg(AgentRun.duration_ms))
            .where(AgentRun.agent_type == tool_key, AgentRun.status == "success")
        )
        avg_latency = avg_result.scalar()

        connectors.append({
            "name": tool_label,
            "key": tool_key,
            "status": "active" if last_run else "ready",
            "latency_ms": round(avg_latency, 1) if avg_latency else 0,
            "last_run": last_run.created_at.isoformat() if last_run else None,
        })

    # 系统运行时间基于最早 agent_run
    first_run_result = await db.execute(
        select(AgentRun.created_at).order_by(AgentRun.created_at.asc()).limit(1)
    )
    first_run = first_run_result.scalar_one_or_none()
    uptime_seconds = 0
    if first_run:
        uptime_seconds = int((datetime.now(timezone.utc) - first_run).total_seconds())

    return {
        "connectors": connectors,
        "uptime_seconds": uptime_seconds,
    }


# 内存日志缓冲区（最近 200 条）
_log_buffer: list[dict] = []


def append_log(level: str, message: str):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
    }
    _log_buffer.append(entry)
    if len(_log_buffer) > 200:
        _log_buffer.pop(0)


@router.get("/logs")
async def get_logs(
    limit: int = 100,
    _admin: User = Depends(require_admin),
):
    if not _log_buffer:
        return {
            "logs": [
                {"timestamp": datetime.now(timezone.utc).isoformat(), "level": "INFO",
                 "message": "EVA 系统已启动，等待 Agent 活动中..."},
            ]
        }
    return {"logs": list(reversed(_log_buffer[-limit:]))}
