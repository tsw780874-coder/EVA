"""Agent service — SSE streaming wrapper (v4: perf timing + smart routing).

Architecture:
  run_pipeline() is called in a background task.
  A token_callback pushes LLM streaming tokens to an asyncio.Queue.
  The main loop drains tokens and yields SSE events concurrently
  with the pipeline execution — so the frontend sees progressive
  output BEFORE the LLM call completes.

v4: Includes perf timing breakdown in final SSE event.
"""

import asyncio
import json
from typing import AsyncGenerator
from app.agent.pipeline import run_pipeline, classify_intent
from app.core.llm import get_available_models, _verified_models
from app.api.v1.admin import append_log

FALLBACK_ORDER = ["deepseek", "openai", "glm47_flash", "glm_flash", "ernie_speed", "ernie35"]


def get_active_fallback() -> str | None:
    for key in FALLBACK_ORDER:
        if _verified_models.get(key, False):
            return key
    models = get_available_models()
    for m in models:
        if m["status"] != "unavailable":
            return m["key"]
    return None


async def run_agent_stream(
    user_query: str,
    chat_history: list[dict] | None = None,
    user_id: str = "",
) -> AsyncGenerator[str, None]:
    # ── 1. Immediate ack (< 1 ms) ──
    yield _sse({"type": "agent_start", "message": "Agent 已启动，正在分析..."})

    # ── 2. Intent (< 1ms) ──
    intent = classify_intent(user_query)
    yield _sse({"type": "agent_progress", "agent": "intent_agent", "message": f"意图分析: {intent}"})

    # ── 3. Build summarized context ──
    context = _build_context(chat_history, user_query)

    # ── 4. No shopping intent → light LLM call ──
    if intent not in ("shopping", "product_query"):
        result = await run_pipeline(
            user_query=context, user_id=user_id, bypass_cache=False,
        )
        yield _sse({"type": "agent_progress", "agent": "analysis_pipeline", "message": "综合分析"})
        if result.get("final_report"):
            yield _sse({"type": "final_report", "markdown": result["final_report"]})
        # Trust metadata (v5)
        yield _sse({"type": "trust", "confidence": result.get("confidence", 100),
                    "data_source": result.get("data_source", "llm"),
                    "citation": result.get("citation", ""),
                    "warning": result.get("confidence_warning")})
        # Include perf timing
        if result.get("perf"):
            yield _sse({"type": "perf", "timing": result["perf"]})
        yield _sse({"type": "done"})
        return

    # ── 5. Shopping flow: concurrent pipeline + token streaming ──
    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=128)

    async def token_callback(text: str):
        await token_queue.put(text)

    pipeline_task = asyncio.create_task(
        run_pipeline(user_query=context, user_id=user_id, stream_callback=token_callback)
    )

    # Drain tokens while pipeline runs
    while not pipeline_task.done():
        try:
            text = await asyncio.wait_for(token_queue.get(), timeout=0.08)
            yield _sse({"type": "token", "text": text, "node": "search_review"})
        except asyncio.TimeoutError:
            pass

    # Drain remaining tokens
    while not token_queue.empty():
        text = token_queue.get_nowait()
        yield _sse({"type": "token", "text": text, "node": "search_review"})

    # ── 6. Pipeline complete ──
    try:
        result = pipeline_task.result()
    except Exception as e:
        append_log("ERROR", f"Agent 异常: {str(e)[:100]}")
        fallback = get_active_fallback()
        hint = f" 系统已自动切换至 {fallback} 模型，请重试。" if fallback else ""
        yield _sse({"type": "error", "message": str(e)[:100] + hint})
        yield _sse({"type": "done"})
        return

    products = result.get("search_results", [])
    if products:
        # Include source markers for transparency
        simulated_count = sum(1 for p in products if p.get("source") == "simulated")
        real_count = len(products) - simulated_count
        msg = f"找到 {len(products)} 个商品"
        if simulated_count > 0:
            msg += f"（{real_count}个真实数据，{simulated_count}个模拟数据）"
        yield _sse({"type": "agent_progress", "agent": "search_agent", "message": msg})
        yield _sse({"type": "agent_result", "agent": "search_agent", "products": products})

    yield _sse({"type": "agent_progress", "agent": "analysis_pipeline", "message": "综合分析"})

    if result.get("final_report"):
        yield _sse({"type": "final_report", "markdown": result["final_report"]})

    # ── 7. Trustworthiness metadata (v5) ──
    yield _sse({"type": "trust", "confidence": result.get("confidence", 0),
                "data_source": result.get("data_source", "unknown"),
                "citation": result.get("citation", ""),
                "warning": result.get("confidence_warning")})

    # ── 8. Perf timing ──
    if result.get("perf"):
        yield _sse({"type": "perf", "timing": result["perf"]})

    yield _sse({"type": "done"})


def _build_context(chat_history: list[dict] | None, current_query: str) -> str:
    """Build summarized context from chat history.

    Strategy: keep last 5 messages verbatim, summarize older messages.
    This keeps context small while preserving recent conversation flow.
    """
    if not chat_history:
        return current_query

    if len(chat_history) <= 6:
        # Small history — just include directly
        lines = []
        for m in chat_history[-6:]:
            role = "用户" if m.get("role") == "user" else "助手"
            content = (m.get("content") or "")[:80]
            if content.strip():
                lines.append(f"{role}: {content}")
        if lines:
            lines.append(f"用户: {current_query}")
            return "\n".join(lines)
        return current_query

    # Longer history — summarize older messages
    recent = chat_history[-5:]
    older = chat_history[:-5]

    # Simple extractive summary: key topics from older messages
    topics = set()
    for m in older:
        content = (m.get("content") or "")[:50]
        if "价格" in content or "price" in content.lower():
            topics.add("曾讨论价格")
        elif "推荐" in content or "recommend" in content.lower():
            topics.add("曾请求推荐")
        elif "对比" in content or "vs" in content.lower():
            topics.add("曾进行对比")

    lines = []
    if topics:
        lines.append(f"[历史摘要: {'; '.join(topics)}]")

    for m in recent:
        role = "用户" if m.get("role") == "user" else "助手"
        content = (m.get("content") or "")[:100]
        if content.strip():
            lines.append(f"{role}: {content}")

    lines.append(f"用户: {current_query}")
    return "\n".join(lines)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
