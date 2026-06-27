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
from app.agent.model_router import route_query
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

FALLBACK_ORDER = ["deepseek", "gemini_flash", "deepseek_flash", "gemini_pro", "openai", "glm47_flash", "glm_flash", "ernie_speed", "ernie35"]


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

    # ── 3. 构建 LLM 上下文（仅LLM用，搜索用纯净 user_query）──
    # v10: 保留完整的 messages 数组结构，LLM 可区分用户/助手角色
    llm_context: list[dict] = _build_context(chat_history, user_query)

    # ── 4. 非购物意图 → 轻量 LLM 调用 ──
    if not is_shopping_intent(intent_result):
        result = await run_pipeline(
            user_query=user_query,
            user_id=user_id,
            bypass_cache=False,
            chat_history=llm_context,
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

    # ── 5. 购物意图 — v2.0 Single LLM Fusion ──
    # v2.0优化: 移除抢占式LLM（可能无响应导致沉默），改用本地状态 + 搜索完成后单次LLM
    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
    ctx_builder = ProgressiveContextBuilder(user_query, intent_result.intent.value)

    async def token_callback(text: str):
        await token_queue.put(text)

    # 5a. 立即发送搜索状态（本地生成，不依赖LLM可用性）
    from app.agent.category_mapper import map_category
    cat = map_category(user_query)
    cat_info = f"「{cat.subcategory}」" if cat.is_valid else ""
    yield _sse({"type": "token", "text": f"正在搜索{cat_info}...", "node": "status"})

    # 5a.5 v10: LLM Tool Planning — 让 LLM 决定调用哪些工具（Function Calling）
    # 仅对购物意图启用，非购物走轻量路径
    tool_results_used = False
    try:
        intent_cfg = route_query(user_query, intent_result.intent.value)
        # 仅对复杂/购物类查询启用工具调用
        if intent_result.intent.value in (
            "buy_product", "compare_products", "recommend_products",
            "price_check", "trend_analysis", "shopping",
        ):
            from app.tools.registry import registry
            from app.tools.executor import executor as tool_executor
            from app.agent.llm_utils import llm_call_with_tools
            from app.agent.eva_system_prompt import get_gateway_prompt

            tool_schemas = registry.get_openai_schemas(role="free")
            planning_prompt = get_gateway_prompt(intent_result.intent.value)
            planning_msg = (
                f"用户查询: {user_query}\n\n"
                f"意图: {intent_result.intent.value}\n"
                f"请判断需要调用哪些工具来获取数据。不需要工具就直接回复'无需工具'。"
            )

            tool_calls, tool_provider, tool_ms = await llm_call_with_tools(
                system_prompt=planning_prompt,
                user_message=planning_msg,
                tools=tool_schemas,
                max_tokens=300,
                temperature=0.2,
                user_id=user_id,
                node_name="tool_planning",
                tool_choice="auto",
            )

            if tool_calls:
                yield _sse({"type": "agent_progress", "agent": "tool_planner",
                           "message": f"AI 决定调用 {len(tool_calls)} 个工具 ({tool_provider}, {tool_ms:.0f}ms)"})

                tool_call_dicts = []
                for tc in tool_calls:
                    tc_dict = {
                        "name": tc.get("function", {}).get("name", tc.get("name", "")),
                        "arguments": tc.get("function", {}).get("arguments", tc.get("arguments", {})),
                    }
                    if isinstance(tc_dict["arguments"], str):
                        try:
                            import json as _json
                            tc_dict["arguments"] = _json.loads(tc_dict["arguments"])
                        except Exception:
                            tc_dict["arguments"] = {}
                    tool_call_dicts.append(tc_dict)
                    yield _sse({"type": "agent_progress", "agent": "tool_call",
                               "message": f"调用工具: {tc_dict['name']}"})

                tool_results = await tool_executor.execute_llm_tool_calls(tool_call_dicts)
                if tool_results:
                    results_list = [
                        {"tool": call_id, "result": tr.to_dict() if hasattr(tr, 'to_dict') else str(tr)}
                        for call_id, tr in tool_results.items()
                    ]
                    await ctx_builder.add_tool_results(results_list)
                    tool_results_used = True
                    for call_id, tr in tool_results.items():
                        data = tr.to_dict() if hasattr(tr, 'to_dict') else {"data": str(tr)}
                        yield _sse({"type": "agent_progress", "agent": "tool_result",
                                   "message": f"工具 {call_id} 完成",
                                   "tool": call_id, "data": data})

                    # ── v10 ReAct Loop: think → act → observe ──
                    # 最多循环 3 步，防止无限推理
                    react_steps = 0
                    max_react_steps = 3
                    while react_steps < max_react_steps:
                        react_steps += 1
                        # 构建观察结果上下文
                        obs_context = "工具执行结果:\n"
                        for call_id, tr in tool_results.items():
                            obs_context += f"[{call_id}]: {tr.to_dict() if hasattr(tr, 'to_dict') else str(tr)[:300]}\n"
                        obs_context += f"\n用户原始查询: {user_query}\n"
                        obs_context += "请判断: 是否需要继续调用更多工具？如果需要，请调用工具；如果不需要，请回复'完成'。"

                        react_calls, react_provider, react_ms = await llm_call_with_tools(
                            system_prompt=planning_prompt,
                            user_message=obs_context,
                            tools=tool_schemas,
                            max_tokens=300,
                            temperature=0.2,
                            user_id=user_id,
                            node_name=f"react_step{react_steps}",
                            tool_choice="auto",
                        )

                        if not react_calls:
                            yield _sse({"type": "agent_progress", "agent": "react",
                                       "message": f"ReAct 步骤{react_steps}: 推理完成"})
                            break

                        # 执行新工具
                        react_call_dicts = []
                        for tc in react_calls:
                            tc_dict = {
                                "name": tc.get("function", {}).get("name", tc.get("name", "")),
                                "arguments": tc.get("function", {}).get("arguments", tc.get("arguments", {})),
                            }
                            if isinstance(tc_dict["arguments"], str):
                                try:
                                    import json as _json
                                    tc_dict["arguments"] = _json.loads(tc_dict["arguments"])
                                except Exception:
                                    tc_dict["arguments"] = {}
                            react_call_dicts.append(tc_dict)
                            yield _sse({"type": "agent_progress", "agent": "react",
                                       "message": f"ReAct 步骤{react_steps}: 调用 {tc_dict['name']}",
                                       "step": react_steps})

                        react_results = await tool_executor.execute_llm_tool_calls(react_call_dicts)
                        if react_results:
                            results_list = [
                                {"tool": cid, "result": tr.to_dict() if hasattr(tr, 'to_dict') else str(tr)}
                                for cid, tr in react_results.items()
                            ]
                            await ctx_builder.add_tool_results(results_list)
                            tool_results = react_results  # 下一轮观察
                        else:
                            break
            else:
                yield _sse({"type": "agent_progress", "agent": "tool_planner",
                           "message": "AI 判断无需额外工具调用，直接搜索"})
    except Exception as e:
        # 工具规划失败不阻塞主流程
        append_log("WARN", f"Tool planning skipped: {type(e).__name__}: {str(e)[:80]}")

    # 5b. Pipeline 搜索（唯一任务 — 不再并行LLM）
    pipeline_task = asyncio.create_task(
        run_pipeline(user_query=user_query, user_id=user_id,
                     stream_callback=token_callback, chat_history=llm_context)
    )

    # 5c. 等待 + 心跳
    last_heartbeat = asyncio.get_event_loop().time()
    while not pipeline_task.done():
        # Drain any tokens from pipeline LLM
        try:
            text = await asyncio.wait_for(token_queue.get(), timeout=0.5)
            yield _sse({"type": "token", "text": text, "node": "search_review"})
            last_heartbeat = asyncio.get_event_loop().time()
        except asyncio.TimeoutError:
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > 2.0:
                yield _sse({"type": "token", "text": "⏳ 搜索进行中...", "node": "heartbeat"})
                last_heartbeat = now

    # Drain remaining tokens
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

    # ── 8. v10: Synchronous Verification Gate — 先验证，再发射 final_report ──
    final_report = result.get("final_report", "")
    verification_passed = True
    verification_warnings: list[str] = []
    verification_action = "allow"

    if final_report:
        # 准备证据
        evidence_list: list = []
        from app.hybrid.types import SourceEvidence, SourceType as HybridSourceType
        rag_docs = result.get("rag_docs", [])
        if rag_docs:
            for doc in rag_docs[:5]:
                evidence_list.append(SourceEvidence(
                    source=HybridSourceType.RAG,
                    content=doc.get("content", "")[:500] if isinstance(doc, dict) else str(doc)[:500],
                    url=doc.get("source", "") if isinstance(doc, dict) else "",
                    relevance_score=doc.get("confidence", 0.5) if isinstance(doc, dict) else 0.5,
                ))
        if products:
            for p in products[:8]:
                p_name = p.get("name", p.get("title", ""))
                p_price = p.get("price", "")
                p_platform = p.get("platform", "")
                content = f"{p_name} | 平台:{p_platform} | 价格:{p_price}"
                evidence_list.append(SourceEvidence(
                    source=HybridSourceType.WEB,
                    content=content,
                    url=p.get("url", ""),
                    relevance_score=p.get("confidence", 0.5),
                ))

        # 执行同步验证（~10-50ms，纯规则引擎，无 LLM 调用）
        try:
            from app.core.verification_gate import VerificationGate
            gate = VerificationGate(threshold=50.0)
            verdict = await gate.verify(final_report, evidence_list, products)
            verification_passed = verdict.passed
            verification_warnings = verdict.warnings
            verification_action = verdict.action

            # 发射验证结果事件
            yield _sse({"type": "verification",
                        "action": verdict.action,
                        "passed": verdict.passed,
                        "confidence": verdict.overall_confidence,
                        "checks": len(verdict.checks),
                        "failed_checks": verdict.failed_checks,
                        "warnings": verdict.warnings})
        except Exception as e:
            append_log("WARN", f"验证门执行异常: {str(e)[:100]}")
            # 验证失败不影响输出 — fall through with warnings

        # ── 根据验证结果决定输出 ──
        if verification_action == "block":
            from app.core.verification_gate import SAFE_FALLBACK_MESSAGE
            yield _sse({"type": "final_report", "markdown": SAFE_FALLBACK_MESSAGE})
        else:
            if verification_action == "flag":
                # 追加警告标记
                flagged_report = final_report
                if verification_warnings:
                    flagged_report += "\n\n> ⚠️ **数据可信度警告**：以下声明未经充分验证，请谨慎参考。\n"
                    for w in verification_warnings[:3]:
                        flagged_report += f"> - {w}\n"
                yield _sse({"type": "final_report", "markdown": flagged_report})
            else:
                yield _sse({"type": "final_report", "markdown": final_report})

    # ── 9. Trust 元数据（含实际验证结果）──
    trust_data = {
        "type": "trust",
        "confidence": result.get("confidence", 0),
        "data_source": result.get("data_source", "unknown"),
        "citation": result.get("citation", ""),
        "warning": result.get("confidence_warning"),
        "freshness_warning": result.get("data_freshness_warning"),
        "data_cached_at": result.get("data_cached_at"),
        "search_layers": result.get("search_layers", []),
        "total_products": result.get("total_products_found", 0),
        "verification_passed": verification_passed,
        "verification_warnings": verification_warnings,
    }
    yield _sse(trust_data)

    # ── 10. Perf timing ──
    if result.get("perf"):
        yield _sse({"type": "perf", "timing": result["perf"]})

    yield _sse({"type": "done"})


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _build_context(chat_history: list[dict] | None, current_query: str) -> list[dict]:
    """v10: Return properly structured messages array for multi-turn LLM context.

    Returns a list of {"role": str, "content": str} dicts suitable for direct
    injection into the LLM messages array.  Maintains role segregation so the
    LLM can distinguish user vs assistant turns.

    Truncation is handled upstream (chat.py keeps last N messages via config).
    """
    if not chat_history:
        return []

    # Return properly typed messages — no flattening, no truncation here
    return [
        {"role": m.get("role", "user"), "content": m.get("content", "")}
        for m in chat_history
        if m.get("content", "").strip()
    ]


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
    # v10: 保留完整的 messages 数组结构
    llm_context: list[dict] = _build_context(chat_history, user_query)

    # ── 3.5. Initial status token → 前端立即看到搜索状态 ──
    try:
        from app.agent.category_mapper import map_category as _map_cat
        _cat = _map_cat(user_query)
        _cat_info = f"「{_cat.subcategory}」" if _cat.is_valid else ""
        yield _sse({"type": "token", "text": f"正在多源搜索{_cat_info}...", "node": "status"})
    except Exception as _e:
        import sys
        print(f"[HYBRID DEBUG] Initial token failed: {_e}", file=sys.stderr)
        yield _sse({"type": "token", "text": "正在多源搜索...", "node": "status"})

    # ── 4. Launch v6 pipeline + HybridAI in parallel ──
    #    v6 pipeline runs the 7-layer product search
    #    HybridAI queries Web, Memory, Tool sources concurrently

    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=128)

    async def token_callback(text: str):
        await token_queue.put(text)

    # HybridAI task (Web + Memory + Tool + source selection)
    hybrid_task = asyncio.create_task(
        hybrid_ai.process(
            user_query=user_query,
            user_id=user_id,
            chat_history=chat_history,
            existing_products=None,  # Will be filled after pipeline completes
            existing_rag_docs=None,
            llm_call_fn=None,  # We'll summarize manually
        )
    )

    # v6 Pipeline task
    pipeline_task = asyncio.create_task(
        run_pipeline(user_query=user_query, user_id=user_id,
                     stream_callback=token_callback, chat_history=llm_context)
    )

    # ── 5. Streaming drain loop — heartbeat + pipeline-first emission ──
    #   核心原则：pipeline 产生数据就立即发射，不等待 hybrid_task
    last_heartbeat = asyncio.get_event_loop().time()
    pipeline_emitted = False  # 防止 pipeline 结果重复发射

    # 预声明变量，避免在循环内声明导致作用域问题
    result: dict = {}
    products: list[dict] = []
    search_layers: list[str] = []
    data_source = "unknown"
    v6_confidence = 0.0

    while not pipeline_task.done() or not hybrid_task.done():
        # ── Drain LLM tokens ──
        try:
            text = await asyncio.wait_for(token_queue.get(), timeout=0.5)
            yield _sse({"type": "token", "text": text, "node": "search_review"})
            last_heartbeat = asyncio.get_event_loop().time()
        except asyncio.TimeoutError:
            # ── Heartbeat: 每 2s 告诉前端"我还活着" ──
            now = asyncio.get_event_loop().time()
            if now - last_heartbeat > 2.0:
                if pipeline_task.done() and not hybrid_task.done():
                    yield _sse({"type": "token", "text": "⏳ 多源情报分析中...", "node": "heartbeat"})
                elif not pipeline_task.done():
                    yield _sse({"type": "token", "text": "⏳ 搜索进行中...", "node": "heartbeat"})
                last_heartbeat = now

        # ── Pipeline 先完成 → 立即发射结果，不等待 hybrid ──
        if pipeline_task.done() and not pipeline_emitted:
            pipeline_emitted = True
            # Drain remaining LLM tokens before emitting results
            while not token_queue.empty():
                text = token_queue.get_nowait()
                yield _sse({"type": "token", "text": text, "node": "search_review"})

            try:
                result = pipeline_task.result()
            except Exception as e:
                append_log("ERROR", f"Hybrid AI pipeline异常: {str(e)[:100]}")
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
            v6_confidence = result.get("confidence", 0)

            # ── Emit products immediately ──
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

            # ── Emit final_report immediately (pipeline version, 不等 hybrid) ──
            v6_report = result.get("final_report", "")
            if v6_report:
                yield _sse({"type": "final_report", "markdown": v6_report})
            elif not products:
                yield _sse({"type": "final_report",
                            "markdown": format_insufficient_data()})

    # Drain remaining tokens
    while not token_queue.empty():
        text = token_queue.get_nowait()
        yield _sse({"type": "token", "text": text, "node": "search_review"})

    # ── 6. Ensure pipeline results (race-condition guard: if loop exited on hybrid) ──
    if not pipeline_emitted:
        try:
            result = pipeline_task.result()
        except Exception as e:
            append_log("ERROR", f"Hybrid AI pipeline异常 (late): {str(e)[:100]}")
            fallback = get_active_fallback()
            hint = f" 系统已自动切换至 {fallback} 模型，请重试。" if fallback else ""
            yield _sse({"type": "final_report", "markdown": f"## ⚠️ 服务暂时不可用\n\n{str(e)[:80]}{hint}"})
            yield _sse({"type": "error", "message": str(e)[:100] + hint})
            yield _sse({"type": "done"})
            return
        products = result.get("search_results", [])
        search_layers = result.get("search_layers", [])
        data_source = result.get("data_source", "unknown")
        v6_confidence = result.get("confidence", 0)
        if products:
            yield _sse({"type": "agent_result", "agent": "search_agent",
                       "products": products, "data_source": data_source,
                       "search_layers": search_layers})
        v6_report = result.get("final_report", "")
        if v6_report:
            yield _sse({"type": "final_report", "markdown": v6_report})

    # ── 7. Get HybridAI result (supplementary — 不阻塞主报告) ──
    try:
        hybrid_result = await hybrid_task
    except Exception as e:
        append_log("WARN", f"HybridAI engine failed: {str(e)[:80]}, falling back to v6 only")
        from app.hybrid.types import HybridResult, SourceType as ST, ConfidenceLevel as CL
        hybrid_result = HybridResult(
            answer=result.get("final_report", ""),
            sources_used=[SourceType.RAG],
            primary_source=SourceType.RAG,
            confidence=v6_confidence,
            confidence_level=CL.HIGH if v6_confidence >= 70 else CL.MEDIUM if v6_confidence >= 40 else CL.LOW,
            warnings=["HybridAI引擎暂时不可用，仅使用v6管线结果。"],
        )

    # ── 8. Emit hybrid supplementary events (metadata only, final_report already sent) ──
    yield _sse({"type": "hybrid_sources", "sources": [
        {"source": s.value, "label": _source_label(s)}
        for s in hybrid_result.sources_used
    ]})

    yield _sse({"type": "hybrid_confidence",
                "confidence": hybrid_result.confidence,
                "level": hybrid_result.confidence_level.value,
                "breakdown": hybrid_result.confidence_breakdown})

    if hybrid_result.conflicts_detected:
        yield _sse({"type": "hybrid_conflict",
                    "conflicts": hybrid_result.conflict_details})

    if not hybrid_result.hallucination_checks_passed:
        yield _sse({"type": "hybrid_guard",
                    "passed": False,
                    "warnings": hybrid_result.warnings})

    # ── 9. Enhanced trust metadata (enriched with hybrid data) ──
    yield _sse({"type": "trust",
                "confidence": hybrid_result.confidence,
                "confidence_level": hybrid_result.confidence_level.value,
                "data_source": data_source,
                "citation": result.get("citation", ""),
                "warning": result.get("confidence_warning"),
                "freshness_warning": result.get("data_freshness_warning"),
                "data_cached_at": result.get("data_cached_at"),
                "search_layers": search_layers,
                "total_products": len(products),
                "hybrid_sources": [s.value for s in hybrid_result.sources_used],
                "hallucination_passed": hybrid_result.hallucination_checks_passed,
                "conflicts": hybrid_result.conflict_details if hybrid_result.conflicts_detected else [],
                })

    # ── 10. Perf timing ──
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
