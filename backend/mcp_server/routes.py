"""MCP Server SSE Transport — HTTP/SSE 端点，与 STDIO transport 并列。

提供:
  GET  /mcp/sse       — SSE 事件流（客户端长连接）
  POST /mcp/message   — JSON-RPC 请求入口（客户端发送请求）
  GET  /mcp/health    — 健康检查

用法（在 app/main.py 中注册）:
    from mcp_server.routes import router as mcp_router
    app.include_router(mcp_router, prefix="/mcp")
"""

import asyncio
import json
import uuid
import time
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from mcp_server.server import TOOLS, TOOL_SCHEMAS

router = APIRouter(tags=["mcp"])

# ── 活跃 SSE 连接池 ──
# {session_id: {"queue": asyncio.Queue, "last_active": float}}
_active_sessions: dict[str, dict] = {}
_SESSION_TIMEOUT = 300  # 5 分钟无活动自动清理


async def _handle_jsonrpc(request: dict) -> dict:
    """处理 JSON-RPC 请求，返回响应 dict。与 STDIO handler 共享逻辑。

    Args:
        request: {"jsonrpc": "2.0", "method": "...", "params": {...}, "id": ...}

    Returns:
        JSON-RPC response dict
    """
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": list(TOOL_SCHEMAS.values())},
        }

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name not in TOOLS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }

        try:
            result = await TOOLS[tool_name](**tool_args)
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"Tool error: {str(e)[:200]}"},
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False),
                    }
                ]
            },
        }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def _cleanup_expired_sessions():
    """清理过期会话。"""
    now = time.time()
    expired = [
        sid for sid, s in _active_sessions.items()
        if now - s["last_active"] > _SESSION_TIMEOUT
    ]
    for sid in expired:
        del _active_sessions[sid]


@router.get("/sse")
async def mcp_sse(request: Request):
    """SSE 端点 — 客户端通过此端点建立长连接接收 MCP 事件。

    首个事件包含 session_id，客户端需在后续 POST /mcp/message 请求中携带。
    """

    session_id = str(uuid.uuid4())[:12]
    queue: asyncio.Queue = asyncio.Queue()
    _active_sessions[session_id] = {"queue": queue, "last_active": time.time()}

    async def event_stream():
        try:
            # 发送 session_id 作为第一个事件
            yield f"data: {json.dumps({'type': 'session', 'session_id': session_id}, ensure_ascii=False)}\n\n"

            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    _active_sessions.get(session_id, {})["last_active"] = time.time()
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    _cleanup_expired_sessions()
                    if session_id not in _active_sessions:
                        break
        except asyncio.CancelledError:
            pass
        finally:
            _active_sessions.pop(session_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/message")
async def mcp_message(request: Request):
    """接收 JSON-RPC 请求并处理。

    请求体:
        {"session_id": "...", "request": {"jsonrpc": "2.0", "method": "...", ...}}

    或直接:
        {"jsonrpc": "2.0", "method": "...", "params": {...}, "id": ...}
    """
    try:
        body = await request.json()
    except Exception:
        return {"jsonrpc": "2.0", "id": 0, "error": {"code": -32700, "message": "Parse error"}}

    # 支持两种请求格式
    session_id = body.get("session_id", "")
    jsonrpc_request = body.get("request", body)

    # 处理 JSON-RPC 请求
    response = await _handle_jsonrpc(jsonrpc_request)

    # 如果有 session，通过 SSE 队列推送同步事件
    if session_id and session_id in _active_sessions:
        session = _active_sessions[session_id]
        try:
            session["queue"].put_nowait({
                "type": "response",
                "response": response,
            })
        except asyncio.QueueFull:
            pass

    return response


@router.get("/health")
async def mcp_health():
    """MCP Server 健康检查。"""
    return {
        "status": "ok",
        "tools_count": len(TOOLS),
        "tools": list(TOOLS.keys()),
        "active_sessions": len(_active_sessions),
        "transports": ["stdio", "sse"],
    }
