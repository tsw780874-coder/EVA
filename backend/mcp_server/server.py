"""
EVA MCP (Model Context Protocol) Server — v8

Supports both STDIO (local dev) and SSE (production) transports.
Exposes 8 tools backed by real backend implementations.

工具列表:
  search_products  → app.tools.product_search
  compare_price    → app.tools.price_compare
  analyze_reviews  → app.tools.review_analyze
  generate_report  → app.agent.pipeline.run_pipeline
  save_memory      → app.services.memory_service.save_memory
  query_memory     → app.services.memory_service.query_memories
  web_search       → app.tools.web_search
  rag_search       → app.tools.rag_search
"""
import json
import asyncio
from typing import Any


# ═══════════════════════════════════════════════════════════════════════
# Tool registry
# ═══════════════════════════════════════════════════════════════════════

TOOLS: dict[str, callable] = {}
TOOL_SCHEMAS: dict[str, dict] = {}


# ═══════════════════════════════════════════════════════════════════════
# MCP 调用追踪 — 实时监控每个工具的调用次数、延迟、错误率
# ═══════════════════════════════════════════════════════════════════════

import time as _time
from collections import defaultdict

_mcp_call_stats: dict[str, dict] = defaultdict(lambda: {
    "total_calls": 0,
    "success_calls": 0,
    "error_calls": 0,
    "total_latency_ms": 0.0,
    "last_call_at": "",
    "last_error": "",
})

_MCP_START_TIME = _time.time()


def _track_call(name: str, success: bool, latency_ms: float, error: str = ""):
    """Record an MCP tool call for monitoring."""
    stats = _mcp_call_stats[name]
    stats["total_calls"] += 1
    if success:
        stats["success_calls"] += 1
    else:
        stats["error_calls"] += 1
        stats["last_error"] = error[:200]
    stats["total_latency_ms"] += latency_ms
    stats["last_call_at"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())


def get_mcp_stats() -> dict:
    """Return current MCP call statistics for monitoring."""
    connectors = []
    for name, schema in TOOL_SCHEMAS.items():
        stats = _mcp_call_stats.get(name, {})
        total = stats.get("total_calls", 0)
        success = stats.get("success_calls", 0)
        avg_latency = (stats.get("total_latency_ms", 0) / total * 1000) if total > 0 else 0
        connectors.append({
            "key": name,
            "name": name,
            "label": schema.get("description", name),
            "status": "active" if total > 0 else "ready",
            "total_calls": total,
            "success_calls": success,
            "error_calls": stats.get("error_calls", 0),
            "avg_latency_us": round(avg_latency),
            "last_call_at": stats.get("last_call_at", ""),
            "last_error": stats.get("last_error", "") if stats.get("error_calls", 0) > 0 else "",
        })
    return {
        "connectors": connectors,
        "uptime_seconds": round(_time.time() - _MCP_START_TIME),
        "total_tools": len(TOOLS),
    }


def register_tool(name: str, description: str = "", parameters: dict | None = None):
    """注册 MCP 工具"""
    def decorator(fn):
        TOOLS[name] = fn
        TOOL_SCHEMAS[name] = {
            "name": name,
            "description": description or (fn.__doc__ or "").split("\n")[0],
            "inputSchema": parameters or {"type": "object", "properties": {}},
        }
        return fn
    return decorator


# ═══════════════════════════════════════════════════════════════════════
# Tool implementations — 调用真实后端
# ═══════════════════════════════════════════════════════════════════════

@register_tool(
    "search_products",
    description="搜索商品信息，支持按名称、品牌、型号搜索。返回商品价格、平台、评分。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "top_k": {"type": "integer", "description": "返回数量", "default": 5},
        },
        "required": ["query"],
    },
)
async def search_products(query: str, top_k: int = 5) -> dict:
    """搜索商品"""
    try:
        from app.tools.product_search import search_products as _search
        result = await _search(query=query, top_k=top_k)
        return result.to_dict()
    except ImportError:
        return {"tool": "search_products", "status": "failed",
                "error": "Tool system unavailable", "data": []}


@register_tool(
    "compare_price",
    description="对比同一商品在京东、天猫、淘宝、得物、拼多多等平台的价格。",
    parameters={
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "商品名称（品牌+型号）"},
            "platforms": {
                "type": "array", "items": {"type": "string"},
                "description": "指定平台列表",
            },
        },
        "required": ["product_name"],
    },
)
async def compare_price(product_name: str, platforms: list[str] | None = None) -> dict:
    """多平台价格对比"""
    try:
        from app.tools.price_compare import compare_price as _compare
        result = await _compare(product_name=product_name, platforms=platforms)
        return result.to_dict()
    except ImportError:
        return {"tool": "compare_price", "status": "failed",
                "error": "Tool system unavailable", "data": []}


@register_tool(
    "analyze_reviews",
    description="分析商品的用户评价和口碑。返回好评率、优缺点分析。",
    parameters={
        "type": "object",
        "properties": {
            "product_name": {"type": "string", "description": "商品名称"},
        },
        "required": ["product_name"],
    },
)
async def analyze_reviews(product_name: str) -> dict:
    """商品评价分析"""
    try:
        from app.tools.review_analyze import analyze_reviews as _analyze
        result = await _analyze(product_name=product_name)
        return result.to_dict()
    except ImportError:
        return {"tool": "analyze_reviews", "status": "failed",
                "error": "Tool system unavailable", "data": []}


@register_tool(
    "generate_report",
    description="生成购物分析报告，包含商品对比、价格分析、购买建议。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "用户查询"},
            "report_type": {
                "type": "string",
                "enum": ["shopping", "price_analysis", "comparison", "recommendation"],
                "description": "报告类型",
            },
        },
        "required": ["query"],
    },
)
async def generate_report(query: str, report_type: str = "shopping") -> dict:
    """生成购物报告"""
    try:
        from app.agent.pipeline import run_pipeline
        result = await run_pipeline(user_query=query, user_id="mcp", bypass_cache=False)
        return {
            "tool": "generate_report",
            "status": "success",
            "data": [{
                "report": result.get("final_report", ""),
                "products": result.get("search_results", []),
                "confidence": result.get("confidence", 0),
                "data_source": result.get("data_source", ""),
            }],
            "source": "agent_pipeline",
            "confidence": result.get("confidence", 0) / 100,
        }
    except ImportError:
        return {"tool": "generate_report", "status": "failed",
                "error": "Pipeline unavailable", "data": []}


@register_tool(
    "save_memory",
    description="保存用户记忆（偏好、已确认信息）。仅存储可信数据，自动过滤推测内容。",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "用户ID"},
            "key": {"type": "string", "description": "记忆键"},
            "value": {"type": "object", "description": "记忆值"},
            "importance": {"type": "number", "description": "重要性 0-1", "default": 0.5},
        },
        "required": ["user_id", "key", "value"],
    },
)
async def save_memory(user_id: str, key: str, value: dict, importance: float = 0.5) -> dict:
    """保存用户记忆"""
    try:
        from app.core.database import async_session
        from app.services.memory_service import save_memory as _save

        async with async_session() as db:
            result = await _save(
                db, user_id, key=key, value=value,
                importance=importance, source="api_result",
            )
            if result is None:
                return {"tool": "save_memory", "status": "failed",
                        "error": "内容未通过安全过滤", "data": []}
            return {
                "tool": "save_memory", "status": "success",
                "data": [{"id": result.id, "key": key}],
                "confidence": 1.0, "source": "memory_system",
            }
    except ImportError:
        return {"tool": "save_memory", "status": "failed",
                "error": "Memory system unavailable", "data": []}


@register_tool(
    "query_memory",
    description="查询用户的历史记忆：偏好、已确认信息、对话摘要。",
    parameters={
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "用户ID"},
            "keyword": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回条数", "default": 10},
        },
        "required": ["user_id"],
    },
)
async def query_memory(user_id: str, keyword: str = "", limit: int = 10) -> dict:
    """查询用户记忆"""
    try:
        from app.tools.memory_query import query_memory as _query
        result = await _query(user_id=user_id, keyword=keyword, limit=limit)
        return result.to_dict()
    except ImportError:
        return {"tool": "query_memory", "status": "failed",
                "error": "Memory system unavailable", "data": []}


@register_tool(
    "web_search",
    description="实时搜索互联网获取最新商品信息、价格动态、新闻。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "max_results": {"type": "integer", "description": "最大结果数", "default": 5},
        },
        "required": ["query"],
    },
)
async def web_search(query: str, max_results: int = 5) -> dict:
    """实时网络搜索"""
    try:
        from app.tools.web_search import search_web as _web
        result = await _web(query=query, max_results=max_results)
        return result.to_dict()
    except ImportError:
        return {"tool": "web_search", "status": "failed",
                "error": "Web search unavailable", "data": []}


@register_tool(
    "rag_search",
    description="搜索内部知识库获取产品评价、购买指南、技术参数。",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"},
            "top_k": {"type": "integer", "description": "返回文档数", "default": 5},
        },
        "required": ["query"],
    },
)
async def rag_search(query: str, top_k: int = 5) -> dict:
    """知识库语义搜索"""
    try:
        from app.tools.rag_search import search_rag as _rag
        result = await _rag(query=query, top_k=top_k)
        return result.to_dict()
    except ImportError:
        return {"tool": "rag_search", "status": "failed",
                "error": "RAG system unavailable", "data": []}


# ═══════════════════════════════════════════════════════════════════════
# Server transports
# ═══════════════════════════════════════════════════════════════════════

async def handle_stdio():
    """Handle JSON-RPC requests over stdin/stdout."""
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, input)
        except EOFError:
            break

        try:
            request = json.loads(line)
            method = request.get("method")
            tool_name = request.get("params", {}).get("name")
            tool_args = request.get("params", {}).get("arguments", {})

            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "tools": list(TOOL_SCHEMAS.values()),
                    },
                }
            elif method == "tools/call" and tool_name in TOOLS:
                t0 = _time.perf_counter()
                try:
                    result = await TOOLS[tool_name](**tool_args)
                    elapsed = (_time.perf_counter() - t0) * 1000
                    _track_call(tool_name, True, elapsed)
                except Exception as exc:
                    _track_call(tool_name, False, 0, str(exc)[:200])
                    result = {"status": "failed", "error": str(exc)}
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False),
                            }
                        ]
                    },
                }
            elif method == "tools/call" and tool_name not in TOOLS:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}",
                    },
                }
            elif method == "mcp/health":
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": get_mcp_stats(),
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"Unknown method: {method}",
                    },
                }

            print(json.dumps(response, ensure_ascii=False), flush=True)

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id", 0) if 'request' in dir() else 0,
                "error": {"code": -32603, "message": str(e)},
            }
            # Track error on tool calls
            if 'tool_name' in dir() and tool_name:
                _track_call(tool_name, False, 0, str(e)[:200])
            print(json.dumps(error_response, ensure_ascii=False), flush=True)


# ═══════════════════════════════════════════════════════════════════════
# SSE Transport (生产环境 HTTP 长连接支持)
# ═══════════════════════════════════════════════════════════════════════

async def handle_sse(scope, receive, send):
    """ASGI SSE transport for MCP tools over HTTP.

    Accepts JSON-RPC requests via POST and streams responses as SSE.
    Compatible with production HTTP servers (uvicorn, gunicorn).
    """
    if scope["type"] == "http" and scope["method"] == "POST":
        # Read request body
        body = b""
        more_body = True
        while more_body:
            msg = await receive()
            body += msg.get("body", b"")
            more_body = msg.get("more_body", False)

        try:
            request = json.loads(body.decode())
            method = request.get("method")
            tool_name = request.get("params", {}).get("name", "unknown")
            tool_args = request.get("params", {}).get("arguments", {})

            if method == "tools/list":
                result = {"tools": list(TOOL_SCHEMAS.values())}
            elif method == "mcp/health":
                result = get_mcp_stats()
            elif method == "tools/call" and tool_name in TOOLS:
                t0 = _time.perf_counter()
                try:
                    result = await TOOLS[tool_name](**tool_args)
                    elapsed = (_time.perf_counter() - t0) * 1000
                    _track_call(tool_name, True, elapsed)
                    # Wrap in MCP content format
                    result = {
                        "content": [
                            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
                        ]
                    }
                except Exception as e:
                    _track_call(tool_name, False, 0, str(e)[:200])
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown method: {method}"}

            response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": "Parse error"}}

        # Send SSE response
        sse_data = f"data: {json.dumps(response, ensure_ascii=False)}\n\n"
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/event-stream"),
                (b"cache-control", b"no-cache"),
                (b"access-control-allow-origin", b"*"),
            ],
        })
        await send({"type": "http.response.body", "body": sse_data.encode()})

    elif scope["method"] == "OPTIONS":
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"access-control-allow-origin", b"*"),
                (b"access-control-allow-methods", b"POST, OPTIONS"),
                (b"access-control-allow-headers", b"content-type"),
            ],
        })
        await send({"type": "http.response.body", "body": b""})


if __name__ == "__main__":
    asyncio.run(handle_stdio())
