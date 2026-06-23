import asyncio
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, insert
from app.api.deps import get_db, require_user
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
    current_user: User = Depends(require_user),
):
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

    # Save user message in background — don't block SSE stream start
    session.updated_at = datetime.now(timezone.utc)
    asyncio.create_task(_save_user_message_async(
        session_id, current_user.id, body.content,
    ))

    append_log("INFO", f"Agent 开始处理: {body.content[:50]}...")

    agent_start = datetime.now(timezone.utc)

    async def event_stream():
        full_reply = ""
        perf_timing: dict = {}
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
            reply_content = full_reply or "分析完成，报告已生成"
            duration_ms = (datetime.now(timezone.utc) - agent_start).total_seconds() * 1000
            now = datetime.now(timezone.utc)

            asyncio.create_task(_persist_results(
                db, session_id, current_user.id, body.content,
                reply_content, duration_ms, now, perf_timing,
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
    current_user: User = Depends(require_user),
):
    """Hybrid AI streaming endpoint — v7 multi-source intelligence.

    Same interface as /stream but adds Web search, Memory, Tool execution,
    conflict resolution, and hallucination guard.
    The original /stream endpoint is preserved unchanged.
    """
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
            reply_content = full_reply or "Hybrid AI 分析完成"
            duration_ms = (datetime.now(timezone.utc) - agent_start).total_seconds() * 1000
            now = datetime.now(timezone.utc)

            asyncio.create_task(_persist_results(
                db, session_id, current_user.id, body.content,
                reply_content, duration_ms, now, perf_timing,
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
) -> None:
    """Persist chat message, report, and agent run in parallel."""
    try:
        async with db.bind.connect() as conn:
            await asyncio.gather(
                conn.execute(
                    insert(ChatMessage).values(
                        id=str(uuid.uuid4()),
                        session_id=session_id,
                        role="assistant",
                        content=reply_content,
                        metadata_={"source": "agent"},
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
                        products=[],
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
            )
            await conn.commit()
    except Exception as e:
        append_log("ERROR", f"持久化失败: {str(e)[:100]}")
