import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, insert
from app.api.deps import get_db, require_user, check_quota, check_rate_limit
from app.models.user import User
from app.models.chat import ChatSession, ChatMessage
from app.models.report import Report
from app.models.agent_run import AgentRun
from app.schemas.chat import (
    ChatSessionResponse, ChatSessionListResponse,
    CreateSessionRequest, SendMessageRequest,
)
from app.services.agent_service import run_agent_stream, run_hybrid_agent_stream
from app.api.v1.admin import append_log

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionListResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    q = (
        select(ChatSession, func.count(ChatMessage.id).label("msg_count"))
        .outerjoin(ChatMessage)
        .where(ChatSession.user_id == current_user.id)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )
    result = await db.execute(q)
    rows = result.all()
    return [
        ChatSessionListResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            message_count=count,
        )
        for s, count in rows
    ]


@router.post("/sessions", response_model=ChatSessionListResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    session = ChatSession(user_id=current_user.id, title=body.title)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionListResponse(id=session.id, title=session.title, created_at=session.created_at, updated_at=session.updated_at, message_count=0)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    q = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    )
    result = await db.execute(q)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    await db.delete(session)
    await db.commit()
    return {"status": "deleted"}


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    from sqlalchemy.orm import selectinload
    q = (
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    result = await db.execute(q)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return ChatSessionResponse.model_validate(session)


@router.post("/sessions/{session_id}/stream")
async def stream_chat(
    session_id: str,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_quota),
):
    # --- Rate limit check ---
    await check_rate_limit(current_user)

    # --- Content safety check ---
    from app.core.content_filter import filter_content
    safety_result = filter_content(body.content)
    if not safety_result.passed:
        raise HTTPException(status_code=400, detail=safety_result.reason)

    # --- Empty/whitespace query check ---
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    # --- Single query: validate session + get history ---
    from sqlalchemy.orm import selectinload
    q = (
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    result = await db.execute(q)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Build chat history from loaded messages (no extra query)
    history = sorted(session.messages or [], key=lambda m: m.created_at)
    chat_history = [{"role": m.role, "content": m.content} for m in history[-20:]]

    # v10修复: 同步等待用户消息保存完成，消除竞态条件
    # _save_user_message_async 使用独立 DB session，不会与主请求 session 冲突
    session.updated_at = datetime.now(timezone.utc)
    await _save_user_message_async(
        session_id, current_user.id, body.content,
    )

    append_log("INFO", f"Agent 开始处理: {body.content[:50]}...")

    agent_start = datetime.now(timezone.utc)

    async def event_stream():
        full_reply = ""
        perf_timing: dict = {}
        captured_products: list[dict] = []
        try:
            async for chunk in run_agent_stream(body.content, chat_history, current_user.id):
                # Extract final_report for persistence
                if "final_report" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        text = data.get("markdown", "")
                        if text:
                            full_reply = text
                    except Exception:
                        pass
                # Capture products from agent_result
                if "agent_result" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        prods = data.get("products", [])
                        if prods:
                            captured_products = prods
                    except Exception:
                        pass
                # Capture perf timing
                if "perf" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        perf_timing = data.get("timing", {})
                    except Exception:
                        pass
                yield chunk

            # Background persistence — don't block stream close
            if not full_reply:
                append_log("WARN", f"Agent 返回空内容 — 所有 LLM provider 可能均已失败")
                full_reply = (
                    "⚠️ **AI 模型暂时不可用**\n\n"
                    "很抱歉，当前所有 AI 模型服务均未能返回有效响应。\n\n"
                    "**可能的原因：**\n"
                    "- AI 模型服务暂时过载或不可用\n"
                    "- 网络连接异常\n\n"
                    "**建议：**\n"
                    "- 请稍后重试\n"
                    "- 系统将自动切换到备用模型\n\n"
                    "---\n"
                    "*EVA 系统会持续监控模型可用性，并在恢复后立即通知。*"
                )
            reply_content = full_reply
            duration_ms = (datetime.now(timezone.utc) - agent_start).total_seconds() * 1000
            now = datetime.now(timezone.utc)

            asyncio.create_task(_persist_results(
                db, session_id, current_user.id, body.content,
                reply_content, duration_ms, now, perf_timing,
                products=captured_products,
            ))

            # Structured perf log
            if perf_timing:
                timing_parts = " | ".join(
                    f"{k}: {v}" for k, v in perf_timing.items()
                )
                append_log("SUCCESS", f"Agent 完成，耗时 {duration_ms:.0f}ms [{timing_parts}]")
            else:
                append_log("SUCCESS", f"Agent 完成，耗时 {duration_ms:.0f}ms")
        except Exception as e:
            append_log("ERROR", f"Agent 异常: {str(e)[:100]}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/stream/hybrid")
async def stream_chat_hybrid(
    session_id: str,
    body: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(check_quota),
):
    """Hybrid AI streaming endpoint — v7 multi-source intelligence.

    Same interface as /stream but adds Web search, Memory, Tool execution,
    conflict resolution, and hallucination guard.
    The original /stream endpoint is preserved unchanged.
    """
    # --- Rate limit check ---
    await check_rate_limit(current_user)

    # --- Content safety check ---
    from app.core.content_filter import filter_content
    safety_result = filter_content(body.content)
    if not safety_result.passed:
        raise HTTPException(status_code=400, detail=safety_result.reason)

    # --- Empty/whitespace query check ---
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    from sqlalchemy.orm import selectinload
    q = (
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    result = await db.execute(q)
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Build chat history
    history = sorted(session.messages or [], key=lambda m: m.created_at)
    chat_history = [{"role": m.role, "content": m.content} for m in history[-20:]]

    # Save user message
    user_msg = ChatMessage(
        session_id=session_id, role="user", content=body.content,
        metadata_={"source": "chat", "pipeline": "hybrid_v7"},
    )
    db.add(user_msg)
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()

    append_log("INFO", f"Hybrid AI 开始处理: {body.content[:50]}...")

    agent_start = datetime.now(timezone.utc)

    async def event_stream():
        full_reply = ""
        perf_timing: dict = {}
        hybrid_meta: dict = {}
        captured_products: list[dict] = []  # Capture products for persistence
        try:
            async for chunk in run_hybrid_agent_stream(body.content, chat_history, current_user.id):
                # Extract final_report for persistence
                if "final_report" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        text = data.get("markdown", "")
                        if text:
                            full_reply = text
                    except Exception:
                        pass
                # Capture products from agent_result for persistence
                if "agent_result" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        products = data.get("products", [])
                        if products:
                            captured_products = products
                    except Exception:
                        pass
                # Capture perf timing
                if "perf" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        perf_timing = data.get("timing", {})
                        hybrid_meta["hybrid_latency_ms"] = data.get("hybrid_latency_ms", 0)
                    except Exception:
                        pass
                # Capture hybrid confidence
                if "hybrid_confidence" in chunk:
                    try:
                        prefix = "data: "
                        data_str = chunk[len(prefix):] if chunk.startswith(prefix) else chunk
                        data = json.loads(data_str)
                        hybrid_meta["confidence"] = data.get("confidence", 0)
                        hybrid_meta["confidence_level"] = data.get("level", "low")
                    except Exception:
                        pass
                yield chunk

            # Background persistence
            if not full_reply:
                append_log("WARN", "Hybrid AI 返回空内容 — 所有 provider 可能均已失败")
                full_reply = (
                    "⚠️ **Hybrid AI 模型暂时不可用**\n\n"
                    "很抱歉，当前所有 AI 模型服务均未能返回有效响应。\n\n"
                    "**建议：**\n"
                    "- 请稍后重试\n"
                    "- 尝试使用标准模式\n\n"
                    "---\n"
                    "*EVA 系统正在自动恢复中。*"
                )
            reply_content = full_reply
            duration_ms = (datetime.now(timezone.utc) - agent_start).total_seconds() * 1000
            now = datetime.now(timezone.utc)

            asyncio.create_task(_persist_results(
                db, session_id, current_user.id, body.content,
                reply_content, duration_ms, now, perf_timing,
                products=captured_products,
            ))

            # Structured perf log
            if perf_timing:
                timing_parts = " | ".join(
                    f"{k}: {v}" for k, v in perf_timing.items()
                )
                h_meta = f" | hybrid_conf={hybrid_meta.get('confidence', '?')}%" if hybrid_meta else ""
                append_log("SUCCESS", f"Hybrid AI 完成，耗时 {duration_ms:.0f}ms [{timing_parts}]{h_meta}")
            else:
                append_log("SUCCESS", f"Hybrid AI 完成，耗时 {duration_ms:.0f}ms")
        except Exception as e:
            append_log("ERROR", f"Hybrid AI 异常: {str(e)[:100]}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/sessions/{session_id}/ws")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
):
    """WebSocket 端点 — 实时双向聊天，作为 SSE 的替代方案。

    客户端发送: {"type": "message", "content": "..."}
    服务端回复: {"type": "token"|"final_report"|"error"|"done", ...}
    """
    await websocket.accept()

    try:
        # 验证 token（从查询参数获取）
        token = websocket.query_params.get("token", "")
        if not token:
            await websocket.send_json({"type": "error", "message": "缺少认证 token"})
            await websocket.close()
            return

        from app.core.security import decode_token
        from app.core.database import async_session
        from app.models.user import User
        from sqlalchemy import select

        try:
            payload = decode_token(token)
            user_id = payload.get("sub")
        except Exception:
            await websocket.send_json({"type": "error", "message": "token 无效"})
            await websocket.close()
            return

        async with async_session() as db:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                await websocket.send_json({"type": "error", "message": "用户不存在"})
                await websocket.close()
                return

            # 验证 session 归属
            from app.models.chat import ChatSession
            from sqlalchemy.orm import selectinload
            q = select(ChatSession).options(selectinload(ChatSession.messages)).where(
                ChatSession.id == session_id, ChatSession.user_id == user_id
            )
            result = await db.execute(q)
            session = result.scalar_one_or_none()
            if not session:
                await websocket.send_json({"type": "error", "message": "会话不存在"})
                await websocket.close()
                return

            # 构建历史
            history = sorted(session.messages or [], key=lambda m: m.created_at)
            chat_history = [{"role": m.role, "content": m.content} for m in history[-20:]]

        # 循环接收消息
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "message":
                content = data.get("content", "")
                if not content.strip():
                    continue

                # 安全检查
                from app.core.content_filter import filter_content
                safety = filter_content(content)
                if not safety.passed:
                    await websocket.send_json({"type": "error", "message": safety.reason})
                    continue

                from app.services.agent_service import run_agent_stream
                from app.services.agent_service import _sse as _ws_sse

                async for chunk in run_agent_stream(content, chat_history, user_id):
                    # 转换 SSE 格式为 JSON
                    if chunk.startswith("data: "):
                        try:
                            event = json.loads(chunk[6:])
                            await websocket.send_json(event)
                        except json.JSONDecodeError:
                            pass

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception:
        pass  # 连接异常关闭


async def _record_price_history(conn, products: list[dict], now):
    """为搜索结果中的每个有价商品记录价格快照。"""
    if not products:
        return
    try:
        from app.models.price_history import PriceHistory
        import uuid as _uuid
        records = []
        for p in products:
            price = p.get("price", 0)
            if isinstance(price, (int, float)) and price > 0:
                pid = p.get("id", hashlib.md5(p.get("name", "").encode()).hexdigest()[:12])
                records.append({
                    "id": str(_uuid.uuid4()),
                    "product_id": pid,
                    "platform": str(p.get("platform", "")),
                    "price": float(price),
                    "original_price": float(p.get("original_price", 0)) if p.get("original_price") else None,
                    "recorded_at": now,
                })
        if records:
            await conn.execute(PriceHistory.__table__.insert(), records)
    except Exception:
        pass  # 价格历史非关键路径，失败不影响主流程


async def _save_user_message_async(
    session_id: str,
    user_id: str,
    content: str,
) -> None:
    """后台保存用户消息 — 使用独立数据库连接，不阻塞 SSE 流启动。"""
    try:
        from app.core.database import async_session
        from app.models.chat import ChatSession
        from sqlalchemy import update

        async with async_session() as db:
            user_msg = ChatMessage(
                session_id=session_id, role="user", content=content,
                metadata_={"source": "chat"},
            )
            db.add(user_msg)
            await db.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(updated_at=datetime.now(timezone.utc))
            )
            await db.commit()
    except Exception as e:
        append_log("ERROR", f"保存用户消息失败: {str(e)[:100]}")


async def _persist_results(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    query: str,
    reply_content: str,
    duration_ms: float,
    now: datetime,
    perf_timing: dict | None = None,
    products: list[dict] | None = None,
) -> None:
    """Persist chat message, report, and agent run in parallel.

    成功持久化后，对非管理员用户扣减1个问题额度。
    """
    try:
        # Build metadata with products for session history restoration
        msg_metadata: dict = {"source": "agent"}
        if products:
            msg_metadata["products"] = products
        if perf_timing:
            msg_metadata["perf"] = perf_timing

        async with db.bind.connect() as conn:
            await asyncio.gather(
                conn.execute(
                    insert(ChatMessage).values(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        role="assistant",
                        content=reply_content,
                        metadata_=msg_metadata,
                        created_at=now,
                    )
                ),
                conn.execute(
                    insert(Report).values(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        title=query[:60],
                        type="agent_report",
                        content={"markdown": reply_content},
                        summary=reply_content[:200],
                        products=products or [],
                        created_at=now,
                    )
                ),
                conn.execute(
                    insert(AgentRun).values(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        agent_type="supervisor",
                        status="success",
                        duration_ms=int(duration_ms),
                        input_data={"query": query},
                        output_data={"report": reply_content[:500], "perf": perf_timing or {}},
                        created_at=now,
                    )
                ),
                # v10: 记录价格历史（每个商品一条快照）
                _record_price_history(conn, products or [], now),
            )
            # 扣减用户额度（管理员不扣减，失败不扣减）
            from app.models.user import User, UserRole
            from sqlalchemy import update
            await conn.execute(
                update(User)
                .where(User.id == user_id, User.role != UserRole.admin, User.remaining_questions > 0)
                .values(
                    remaining_questions=User.remaining_questions - 1,
                    total_questions_used=User.total_questions_used + 1,
                )
            )
            await conn.commit()

        # v10: 后台自动摘要（不阻塞主流程）
        asyncio.create_task(_auto_summarize_background(user_id, session_id, query, reply_content))

    except Exception as e:
        append_log("ERROR", f"持久化失败: {str(e)[:100]}")


async def _auto_summarize_background(user_id: str, session_id: str, query: str, reply: str):
    """后台自动生成记忆摘要。"""
    try:
        from app.services.memory_service import auto_summarize_session
        saved = await auto_summarize_session(user_id, session_id, query, reply)
        if saved > 0:
            append_log("SUCCESS", f"记忆自动化: 从会话 {session_id[:8]} 提取了 {saved} 条记忆")
    except Exception as e:
        append_log("DEBUG", f"记忆自动化跳过: {type(e).__name__}")
