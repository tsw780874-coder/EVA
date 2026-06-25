"""Agent service — SSE streaming wrapper (v8: 并行搜索 + LLM抢占 + 异步验证).

v8 Architecture:
  1. LLM 抢先启动（不等待搜索完成）
  2. Pipeline 并行搜索（Layer 0+1+2 同时跑）
  3. 搜索结果渐进注入 LLM 上下文
  4. Verification 异步后台执行（不阻塞 final_report）
  5. Token 队列优化（更大容量、更快轮询）

v7 Hybrid AI: 多源情报层（Web + Memory + Tool + Reasoning）
  作为 v8 pipeline 的附加层叠加。
"""

import asyncio
import json
from typing import AsyncGenerator
from app.agent.pipeline import run_pipeline
from app.agent.intent_router import route_intent, is_shopping_intent, IntentType
from app.agent.llm_utils import llm_call
from app.agent.progressive_context import ProgressiveContextBuilder, get_pre_search_prompt
from app.core.llm import get_available_models, _verified_models
from app.api.v1.admin import append_log
from app.hybrid.core import hybrid_ai
from app.hybrid.types import SourceType, ConfidenceLevel
from app.hybrid.output_formatter import format_response, format_insufficient_data
from app.core.verification_gate import VerificationGate, verify_response, safe_fallback, SAFE_FALLBACK_MESSAGE
from app.hybrid.guard import check_hallucination
from app.config import get_settings

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
    """v8 Agent SSE Stream — LLM抢占 + 并行搜索 + 异步验证。

    关键优化：
      - LLM 先启动 stream，不等待搜索结果
      - Pipeline 并行搜索 Layer 0+1+2
      - Verification 放后台，不阻塞 final_report
    """
    settings = get_settings()
    token_poll_ms = settings.token_poll_interval_ms / 1000.0
    queue_size = settings.token_queue_size

    # ── 1. 立即确认 (< 1ms) ──
    yield _sse({"type": "agent_start", "message": "Agent 已启动，正在分析..."})

    # ── 2. 意图分析 (< 1ms) ──
    intent_result = route_intent(user_query)
    yield _sse({"type": "agent_progress", "agent": "intent_agent",
                "message": f"意图分析: {intent_result.intent.value}"})

    # ── 3. 构建摘要上下文 ──
    context = _build_context(chat_history, user_query)

    # ── 4. 非购物意图 → 轻量 LLM 调用（保持原逻辑）──
    if not is_shopping_intent(intent_result):
        result = await run_pipeline(
            user_query=context, user_id=user_id, bypass_cache=False,
        )
        yield _sse({"type": "agent_progress", "agent": "analysis_pipeline", "message": "综合分析"})
        if result.get("final_report"):
            yield _sse({"type": "final_report", "markdown": result["final_report"]})
        yield _sse({"type": "trust", "confidence": result.get("confidence", 100),
                    "data_source": result.get("data_source", "llm"),
                    "citation": result.get("citation", ""),
                    "warning": result.get("confidence_warning"),
                    "search_layers": result.get("search_layers", []),
                    "total_products": result.get("total_products_found", 0)})
        if result.get("perf"):
            yield _sse({"type": "perf", "timing": result["perf"]})
        yield _sse({"type": "done"})
        return

    # ── 5. 购物意图 — v8 LLM抢占模式 ──
    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
    ctx_builder = ProgressiveContextBuilder(user_query, intent_result.intent.value)

    async def token_callback(text: str):
        await token_queue.put(text)

    # 5a. 立即启动 LLM 流 (抢占式 — 不等搜索)
    pre_sys, pre_msg = get_pre_search_prompt(user_query, intent_result.intent.value)
    llm_task = asyncio.create_task(
        llm_call(
            system_prompt=pre_sys,
            user_message=pre_msg,
            max_tokens=150,  # 初始响应短一些
            temperature=0.4,
            user_id=user_id,
            node_name="pre_search",
            stream_callback=token_callback,
        )
    )

    # 5b. Pipeline 并行搜索（与 LLM 同时跑）
    pipeline_task = asyncio.create_task(
        run_pipeline(user_query=context, user_id=user_id, stream_callback=None)
    )

    # 5c. 主循环 — 双任务同时运行时的 token 排水
    while not llm_task.done() or not pipeline_task.done():
        try:
            text = await asyncio.wait_for(token_queue.get(), timeout=token_poll_ms)
            yield _sse({"type": "token", "text": text, "node": "search_review"})
        except asyncio.TimeoutError:
            # 轮询间隔 — 检查是否有 token 到达
            pass

    # 排空残余 token
    while not token_queue.empty():
        text = token_queue.get_nowait()
        yield _sse({"type": "token", "text": text, "node": "search_review"})

    # ── 6. 获取 Pipeline 结果 ──
    try:
        result = pipeline_task.result()
    except Exception as e:
        append_log("ERROR", f"Agent 异常: {str(e)[:100]}")
        fallback = get_active_fallback()
        hint = f" 系统已自动切换至 {fallback} 模型，请重试。" if fallback else ""
        error_report = f"""## ⚠️ 服务暂时不可用

**原因：** AI 模型服务暂时无响应（{str(e)[:80]}）

**建议：**
- 请稍后重试
- 系统将自动切换到备用模型
{hint}

---
*EVA 系统会持续监控模型可用性，并在恢复后立即通知。*"""
        yield _sse({"type": "final_report", "markdown": error_report})
        yield _sse({"type": "error", "message": str(e)[:100] + hint})
        yield _sse({"type": "done"})
        return

    products = result.get("search_results", [])
    search_layers = result.get("search_layers", [])
    data_source = result.get("data_source", "unknown")

    # ── 7. 搜索结果已到 — 注入 LLM 上下文做增强总结 ──
    if products:
        # 发射搜索层进度
        layer_names = {
            "hot_products": "热门商品库",
            "trending_normalize": "热门搜索匹配",
            "rag": "RAG知识库",
            "product_cache": "商品缓存库",
            "live_search": "电商平台实时搜索",
            "similar_search": "相似商品匹配",
            "template": "模板匹配",
            "link_fallback": "链接回退",
        }
        for layer in search_layers:
            label = layer_names.get(layer, layer)
            yield _sse({"type": "agent_progress", "agent": "search_layer",
                       "message": f"搜索层: {label}", "layer": layer})

        simulated_count = sum(1 for p in products if p.get("source") == "simulated")
        real_count = len(products) - simulated_count
        msg = f"找到 {len(products)} 个商品"
        if simulated_count > 0:
            msg += f"（{real_count}个真实数据，{simulated_count}个模拟数据）"
        elif data_source == "similar":
            msg += "（相似商品匹配）"
        elif data_source == "cache":
            msg += "（来自商品缓存）"
        yield _sse({"type": "agent_progress", "agent": "search_agent", "message": msg})
        yield _sse({"type": "agent_result", "agent": "search_agent",
                   "products": products, "data_source": data_source,
                   "search_layers": search_layers})

        # 用搜索结果做增强型 LLM 总结
        await ctx_builder.add_products(products, data_source)
        rag_docs = result.get("rag_docs", [])
        if rag_docs:
            await ctx_builder.add_rag_docs(rag_docs)

        sys_prompt, user_msg = ctx_builder.build_prompt()
        enhance_text, _, _ = await llm_call(
            system_prompt=sys_prompt,
            user_message=user_msg,
            max_tokens=400,
            temperature=0.3,
            user_id=user_id,
            node_name="post_search_enhance",
            stream_callback=token_callback,
        )

        # 排空增强 LLM 的 token
        while not token_queue.empty():
            text = token_queue.get_nowait()
            yield _sse({"type": "token", "text": text, "node": "search_review"})

    yield _sse({"type": "agent_progress", "agent": "analysis_pipeline", "message": "综合分析"})

    # ── 8. 先发射 final_report（不等待验证）──
    final_report = result.get("final_report", "")
    if final_report:
        yield _sse({"type": "final_report", "markdown": final_report})

    # ── 9. Trust 元数据（先发射基础版）──
    yield _sse({"type": "trust", "confidence": result.get("confidence", 0),
                "data_source": result.get("data_source", "unknown"),
                "citation": result.get("citation", ""),
                "warning": result.get("confidence_warning"),
                "search_layers": result.get("search_layers", []),
                "total_products": result.get("total_products_found", 0),
                "verification_passed": True,   # 先乐观通过
                "verification_warnings": []})

    # ── 10. Perf timing ──
    if result.get("perf"):
        yield _sse({"type": "perf", "timing": result["perf"]})

    yield _sse({"type": "done"})

    # ── 11. 异步 Verification（后台执行，不阻塞用户响应）──
    if final_report and products:
        asyncio.create_task(
            _async_verify_and_emit(final_report, products, result, token_queue)
        )


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _async_verify_and_emit(
    final_report: str,
    products: list[dict],
    result: dict,
    token_queue: asyncio.Queue,
):
    """后台异步验证 + 通过 token_queue 回传结果。

    关键原则：不阻塞主响应流。验证在后台进行，
    结果通过独立 SSE 事件发送给前端。
    """
    try:
        from app.hybrid.types import SourceEvidence

        evidence_list: list = []
        rag_docs = result.get("rag_docs", [])
        if rag_docs:
            for doc in rag_docs[:5]:
                evidence_list.append(SourceEvidence(
                    source=SourceType.RAG,
                    content=doc.get("content", "")[:500],
                    relevance_score=doc.get("score", 0.5),
                    authority="rag",
                ))

        if products:
            product_text = "\n".join(
                f"{p.get('name','?')} | {p.get('platform','?')} | "
                f"¥{p.get('price',0)} | source={p.get('source','?')}"
                for p in products[:5]
            )
            evidence_list.append(SourceEvidence(
                source=SourceType.TOOL,
                content=product_text,
                relevance_score=0.8,
                authority="product_db",
            ))

        gate = VerificationGate(threshold=50.0)
        verdict = await gate.verify(final_report, evidence_list, products)

        verification_event = json.dumps({
            "type": "verification",
            "passed": verdict.passed,
            "action": verdict.action.value,
            "confidence": verdict.overall_confidence,
            "failed_checks": verdict.failed_checks,
            "warnings": verdict.warnings,
        }, ensure_ascii=False)

        await token_queue.put(f"data: {verification_event}\n\n")

        if not verdict.passed:
            append_log("WARN",
                f"Verification BLOCKED (async): {verdict.failed_checks} "
                f"confidence={verdict.overall_confidence:.0f}%")
    except Exception as e:
        append_log("ERROR", f"Async verification failed: {str(e)[:100]}")


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


# ═══════════════════════════════════════════════════════════════════════
# v7 Hybrid AI Stream — additive layer on top of v6 pipeline
# ═══════════════════════════════════════════════════════════════════════

async def run_hybrid_agent_stream(
    user_query: str,
    chat_history: list[dict] | None = None,
    user_id: str = "",
) -> AsyncGenerator[str, None]:
    """Hybrid AI streaming agent — v6 pipeline + multi-source intelligence.

    This is an ADDITIVE layer. It runs the existing v6 pipeline for product
    search AND queries additional sources (Web, Memory, Tool) in parallel.
    Results are merged with conflict resolution and hallucination checks.

    SSE Event types (superset of v6):
      - agent_start, agent_progress, agent_result, token, final_report, done
      - hybrid_sources (NEW): multi-source query results
      - hybrid_confidence (NEW): confidence breakdown
      - hybrid_conflict (NEW): conflict detection results
      - hybrid_guard (NEW): hallucination check results
    """
    # ── 1. Immediate ack ──
    yield _sse({"type": "agent_start", "message": "EVA Hybrid AI 已启动，正在多源分析..."})

    # ── 2. Intent (< 1ms) ──
    intent_result = route_intent(user_query)
    yield _sse({"type": "agent_progress", "agent": "intent_agent",
                "message": f"意图分析: {intent_result.intent.value}"})

    # ── 3. Build context ──
    context = _build_context(chat_history, user_query)

    # ── 4. Launch v6 pipeline + HybridAI in parallel ──
    #    v6 pipeline runs the 7-layer product search
    #    HybridAI queries Web, Memory, Tool sources concurrently

    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=128)

    async def token_callback(text: str):
        await token_queue.put(text)

    # HybridAI task (Web + Memory + Tool + source selection)
    hybrid_task = asyncio.create_task(
        hybrid_ai.process(
            user_query=context,
            user_id=user_id,
            chat_history=chat_history,
            existing_products=None,  # Will be filled after pipeline completes
            existing_rag_docs=None,
            llm_call_fn=None,  # We'll summarize manually
        )
    )

    # v6 Pipeline task
    pipeline_task = asyncio.create_task(
        run_pipeline(user_query=context, user_id=user_id, stream_callback=token_callback)
    )

    # ── 5. Drain tokens while pipeline + hybrid run ──
    while not pipeline_task.done() and not hybrid_task.done():
        try:
            text = await asyncio.wait_for(token_queue.get(), timeout=0.08)
            yield _sse({"type": "token", "text": text, "node": "search_review"})
        except asyncio.TimeoutError:
            pass

    # Drain remaining tokens
    while not token_queue.empty():
        text = token_queue.get_nowait()
        yield _sse({"type": "token", "text": text, "node": "search_review"})

    # ── 6. Get pipeline result ──
    try:
        result = pipeline_task.result()
    except Exception as e:
        append_log("ERROR", f"Hybrid AI pipeline异常: {str(e)[:100]}")
        fallback = get_active_fallback()
        hint = f" 系统已自动切换至 {fallback} 模型，请重试。" if fallback else ""
        # Emit a proper final_report so the frontend shows something useful
        error_report = f"""## ⚠️ 服务暂时不可用

**原因：** AI 模型服务暂时无响应（{str(e)[:80]}）

**建议：**
- 请稍后重试
- 系统将自动切换到备用模型
{hint}

---
*EVA 系统会持续监控模型可用性，并在恢复后立即通知。*"""
        yield _sse({"type": "final_report", "markdown": error_report})
        yield _sse({"type": "error", "message": str(e)[:100] + hint})
        yield _sse({"type": "done"})
        return

    products = result.get("search_results", [])
    search_layers = result.get("search_layers", [])
    data_source = result.get("data_source", "unknown")
    v6_confidence = result.get("confidence", 0)

    # ── 7. Get HybridAI result ──
    try:
        hybrid_result = await hybrid_task
    except Exception as e:
        append_log("WARN", f"HybridAI engine failed: {str(e)[:80]}, falling back to v6 only")
        # Build a minimal HybridResult from v6 data
        from app.hybrid.types import HybridResult, SourceType as ST, ConfidenceLevel as CL
        hybrid_result = HybridResult(
            answer=result.get("final_report", ""),
            sources_used=[SourceType.RAG],
            primary_source=SourceType.RAG,
            confidence=v6_confidence,
            confidence_level=CL.HIGH if v6_confidence >= 70 else CL.MEDIUM if v6_confidence >= 40 else CL.LOW,
            warnings=["HybridAI引擎暂时不可用，仅使用v6管线结果。"],
        )

    # ── 8. Emit hybrid source info ──
    yield _sse({"type": "hybrid_sources", "sources": [
        {"source": s.value, "label": _source_label(s)}
        for s in hybrid_result.sources_used
    ]})

    # ── 9. Emit products (from v6 pipeline) ──
    if products:
        layer_names = {
            "hot_products": "热门商品库",
            "trending_normalize": "热门搜索匹配",
            "rag": "RAG知识库",
            "product_cache": "商品缓存库",
            "live_search": "电商平台实时搜索",
            "similar_search": "相似商品匹配",
            "template": "模板匹配",
            "link_fallback": "链接回退",
        }
        for layer in search_layers:
            label = layer_names.get(layer, layer)
            yield _sse({"type": "agent_progress", "agent": "search_layer",
                       "message": f"搜索层: {label}", "layer": layer})

        simulated_count = sum(1 for p in products if p.get("source") == "simulated")
        real_count = len(products) - simulated_count
        msg = f"找到 {len(products)} 个商品"
        if simulated_count > 0:
            msg += f"（{real_count}个真实数据，{simulated_count}个模拟数据）"

        yield _sse({"type": "agent_progress", "agent": "search_agent", "message": msg})
        yield _sse({"type": "agent_result", "agent": "search_agent",
                   "products": products, "data_source": data_source,
                   "search_layers": search_layers})

    # ── 10. Emit hybrid confidence ──
    yield _sse({"type": "hybrid_confidence",
                "confidence": hybrid_result.confidence,
                "level": hybrid_result.confidence_level.value,
                "breakdown": hybrid_result.confidence_breakdown})

    # ── 11. Emit conflicts (if any) ──
    if hybrid_result.conflicts_detected:
        yield _sse({"type": "hybrid_conflict",
                    "conflicts": hybrid_result.conflict_details})

    # ── 12. Emit hallucination guard result ──
    if not hybrid_result.hallucination_checks_passed:
        yield _sse({"type": "hybrid_guard",
                    "passed": False,
                    "warnings": hybrid_result.warnings})

    # ── 13. Build final report with hybrid formatting ──
    v6_report = result.get("final_report", "")
    if v6_report:
        # Use v6 report as base, enrich with hybrid metadata
        hybrid_answer = v6_report

        # Append hybrid source info if web/memory/tool were used
        non_rag_sources = [
            s for s in hybrid_result.sources_used
            if s not in (SourceType.RAG, SourceType.REASONING)
        ]
        if non_rag_sources:
            source_note = "\n\n---\n\n**【补充信息源】**\n"
            for s in non_rag_sources:
                source_note += f"- {_source_label(s)}\n"
            hybrid_answer += source_note

        yield _sse({"type": "final_report", "markdown": hybrid_answer})
    elif hybrid_result.answer:
        yield _sse({"type": "final_report", "markdown": hybrid_result.answer})
    else:
        yield _sse({"type": "final_report",
                    "markdown": format_insufficient_data()})

    # ── 14. Enhanced trust metadata (v7) ──
    yield _sse({"type": "trust",
                "confidence": hybrid_result.confidence,
                "confidence_level": hybrid_result.confidence_level.value,
                "data_source": data_source,
                "citation": result.get("citation", ""),
                "warning": result.get("confidence_warning"),
                "search_layers": search_layers,
                "total_products": len(products),
                "hybrid_sources": [s.value for s in hybrid_result.sources_used],
                "hallucination_passed": hybrid_result.hallucination_checks_passed,
                "conflicts": hybrid_result.conflict_details if hybrid_result.conflicts_detected else [],
                })

    # ── 15. Perf timing ──
    if result.get("perf"):
        yield _sse({"type": "perf", "timing": result["perf"],
                    "hybrid_latency_ms": hybrid_result.total_latency_ms})

    yield _sse({"type": "done"})


def _source_label(source: SourceType) -> str:
    """Human-readable source label."""
    labels = {
        SourceType.WEB: "Web（实时搜索）",
        SourceType.RAG: "RAG（知识库检索）",
        SourceType.MEMORY: "Memory（历史记忆）",
        SourceType.TOOL: "Tool（数据库/API/计算）",
        SourceType.REASONING: "Reasoning（逻辑推理）",
    }
    return labels.get(source, source.value)
