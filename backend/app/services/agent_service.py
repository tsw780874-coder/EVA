"""Agent service — SSE streaming wrapper (v3: direct pipeline, no LangGraph).

Architecture:
  run_pipeline() is called in a background task.
  A token_callback pushes LLM streaming tokens to an asyncio.Queue.
  The main loop drains tokens and yields SSE events concurrently
  with the pipeline execution — so the frontend sees progressive
  output BEFORE the LLM call completes.

Total LLM calls: 1 (combined search+review).
Total graph hops: 0.
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
    # --- 1. Immediate ack (< 1 ms) ---
    yield _sse({"type": "agent_start", "message": "Agent 已启动，正在分析..."})

    # --- 2. Intent ---
    intent = classify_intent(user_query)
    yield _sse({"type": "agent_progress", "agent": "intent_agent", "message": f"意图分析: {intent}"})

    # No shopping intent → skip LLM, go straight to report
    if intent not in ("shopping", "product_query"):
        result = await run_pipeline(user_query=user_query, user_id=user_id)
        yield _sse({"type": "agent_progress", "agent": "analysis_pipeline", "message": "综合分析"})
        if result.get("final_report"):
            yield _sse({"type": "final_report", "markdown": result["final_report"]})
        yield _sse({"type": "done"})
        return

    # --- 3. Shopping flow: concurrent pipeline + token streaming ---
    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=128)

    async def token_callback(text: str):
        await token_queue.put(text)

    pipeline_task = asyncio.create_task(
        run_pipeline(user_query=user_query, user_id=user_id, stream_callback=token_callback)
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

    # --- 4. Pipeline complete ---
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
        yield _sse({"type": "agent_progress", "agent": "search_agent", "message": f"找到 {len(products)} 个商品"})
        yield _sse({"type": "agent_result", "agent": "search_agent", "products": products})

    yield _sse({"type": "agent_progress", "agent": "analysis_pipeline", "message": "综合分析"})

    if result.get("final_report"):
        yield _sse({"type": "final_report", "markdown": result["final_report"]})

    yield _sse({"type": "done"})


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
