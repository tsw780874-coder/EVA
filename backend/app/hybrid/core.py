"""Hybrid AI Core Engine — Multi-Source Intelligent Decision Orchestrator.

Implements the 12-rule EVA Hybrid AI framework as an additive layer
on top of the existing v6 product search pipeline.

Architecture:
  User Query
    → SourceSelector (analyze question, pick sources)
    → Parallel Source Query (RAG, Web, Memory, Tool)
    → Conflict Resolver (Web > RAG > Memory)
    → Hallucination Guard (validate claims)
    → Output Formatter (structured response)

IMPORTANT: This module is an ADDITIVE layer. It does NOT replace:
  - pipeline.py (v6 product search pipeline)
  - agent_service.py (SSE streaming service)
  - Existing RAG, cache, or search layers

Instead, it ENHANCES them with:
  - Web search capability (new)
  - Structured source selection (new)
  - Conflict detection/resolution (new)
  - Anti-hallucination guard (new)
  - Mandatory output format (new)
"""

import asyncio
import time
from typing import Callable, Awaitable

from app.hybrid.types import (
    SourceType, QuestionType, ConfidenceLevel,
    SourceEvidence, SourceResult, HybridResult,
)
from app.hybrid.source_selector import select_sources, needs_escalation
from app.hybrid.web_search import web_search
from app.hybrid.tool_executor import execute_tool_query, compute_confidence_breakdown
from app.hybrid.reasoner import decompose_and_reason, synthesize_conclusions
from app.hybrid.conflict_resolver import detect_conflicts, resolve, format_conflict_report
from app.hybrid.guard import check_hallucination, sanitize_response
from app.hybrid.output_formatter import format_response, format_insufficient_data
from app.api.v1.admin import append_log


class HybridAI:
    """Central Hybrid AI engine — orchestrates multi-source intelligence.

    Usage:
        engine = HybridAI()
        result = await engine.process(
            user_query="iPhone 16 最新价格对比",
            user_id="user-123",
            chat_history=[],
            existing_products=[],  # from v6 pipeline
            llm_call_fn=None,      # optional LLM summarizer
        )
    """

    def __init__(self):
        self._source_stats: dict[str, int] = {
            "rag_hits": 0, "web_hits": 0, "memory_hits": 0,
            "tool_hits": 0, "escalations": 0,
        }

    # ═══════════════════════════════════════════════════════════════
    # Main processing pipeline
    # ═══════════════════════════════════════════════════════════════

    async def process(
        self,
        user_query: str,
        user_id: str = "",
        chat_history: list[dict] | None = None,
        existing_products: list[dict] | None = None,
        existing_rag_docs: list[dict] | None = None,
        llm_call_fn: Callable[..., Awaitable[tuple[str, str, float]]] | None = None,
    ) -> HybridResult:
        """Process a user query through the Hybrid AI pipeline.

        Args:
            user_query: The user's question
            user_id: Current user ID for memory/tool queries
            chat_history: Previous conversation messages
            existing_products: Products already found by v6 pipeline
            existing_rag_docs: RAG documents already retrieved
            llm_call_fn: Optional LLM summarization function
                         (system_prompt, user_message, max_tokens, temperature, ...)
                         → (content, provider, elapsed_ms)

        Returns:
            HybridResult with answer, sources, confidence, and metadata
        """
        t_start = time.perf_counter()

        # ── Step 1: Analyze question + select sources ──
        plan = select_sources(user_query)
        append_log("DEBUG",
            f"HybridAI: qtype={plan.question_type.value} "
            f"primary={[s.value for s in plan.primary_sources]} "
            f"requires_web={plan.requires_web}"
        )

        # ── Step 2: Query information sources (parallel where possible) ──
        source_results: dict[SourceType, SourceResult] = {}

        # Build list of coroutines to execute in parallel
        tasks = []

        # RAG — reuse existing if available, otherwise query
        if SourceType.RAG in plan.primary_sources:
            if existing_rag_docs:
                # Wrap existing docs as SourceResult
                evidence = [
                    SourceEvidence(
                        source=SourceType.RAG,
                        content=doc.get("content", "")[:500],
                        relevance_score=doc.get("score", 0.5),
                        authority="rag",
                    )
                    for doc in existing_rag_docs[:5]
                ]
                source_results[SourceType.RAG] = SourceResult(
                    source=SourceType.RAG,
                    success=len(evidence) > 0,
                    evidence=evidence,
                    latency_ms=0.0,
                )
            else:
                tasks.append(("rag", self._query_rag(user_query)))

        # Web — query if required or in primary sources
        if SourceType.WEB in plan.primary_sources or plan.requires_web:
            tasks.append(("web", web_search(user_query)))

        # Memory — query if historical context needed
        if SourceType.MEMORY in plan.primary_sources or plan.requires_memory:
            tasks.append(("memory", self._query_memory(user_query, user_id, chat_history)))

        # Tool — query if computation/data needed
        if SourceType.TOOL in plan.primary_sources or plan.requires_tool:
            tasks.append(("tool", execute_tool_query(
                user_query, user_id=user_id, products=existing_products,
            )))

        # Execute non-RAG tasks in parallel
        if tasks:
            parallel_results = await asyncio.gather(
                *[t[1] for t in tasks],
                return_exceptions=True,
            )
            for (name, _), result in zip(tasks, parallel_results):
                if isinstance(result, Exception):
                    append_log("WARN", f"HybridAI source '{name}' failed: {str(result)[:80]}")
                    source_results[SourceType(name)] = SourceResult(
                        source=SourceType(name),
                        success=False,
                        error=str(result)[:100],
                    )
                else:
                    source_results[SourceType(name)] = result

        # ── Step 3: Check if escalation needed ──
        all_evidence: list[SourceEvidence] = []
        for sr in source_results.values():
            if sr.success:
                all_evidence.extend(sr.evidence)

        escalated = False
        if needs_escalation(
            {k: v.evidence for k, v in source_results.items() if v.success},
            threshold=plan.escalation_threshold,
        ):
            # Escalate to fallback sources
            escalated = True
            self._source_stats["escalations"] += 1
            append_log("INFO", f"HybridAI: escalating to fallback sources: "
                      f"{[s.value for s in plan.fallback_sources]}")

            for fb_source in plan.fallback_sources:
                if fb_source not in source_results:
                    try:
                        if fb_source == SourceType.WEB:
                            fb_result = await web_search(user_query)
                        elif fb_source == SourceType.RAG:
                            fb_result = await self._query_rag(user_query)
                        elif fb_source == SourceType.MEMORY:
                            fb_result = await self._query_memory(user_query, user_id, chat_history)
                        elif fb_source == SourceType.TOOL:
                            fb_result = await execute_tool_query(user_query, user_id=user_id)
                        else:
                            continue

                        source_results[fb_source] = fb_result
                        if fb_result.success:
                            all_evidence.extend(fb_result.evidence)
                    except Exception as e:
                        append_log("ERROR", f"HybridAI fallback '{fb_source.value}' failed: {str(e)[:80]}")

        # ── Step 4: Multi-step reasoning (for complex questions) ──
        reasoning_text = ""
        reasoning_confidence = 0.0
        if plan.requires_decomposition:
            reasoning_plan = decompose_and_reason(user_query)
            append_log("DEBUG", f"HybridAI: decomposed into {len(reasoning_plan.steps)} steps "
                      f"({reasoning_plan.decomposition_strategy})")

            # For now, reasoning synthesizes from available evidence
            # In production, each step would query its own sources
            if all_evidence or existing_products:
                evidence_summary = "\n".join(
                    ev.content[:300] for ev in all_evidence[:5]
                )
                reasoning_text = (
                    f"基于以下信息进行推理分析：\n\n{evidence_summary}\n\n"
                )
                reasoning_confidence = 60.0
            else:
                reasoning_text = "推理引擎需要更多信息才能给出有效结论。"
                reasoning_confidence = 10.0

        # ── Step 5: Detect and resolve conflicts ──
        conflicts = detect_conflicts(all_evidence)
        resolved_evidence, conflict_notes = resolve(conflicts, all_evidence)

        # ── Step 6: Compute confidence ──
        sources_used = [
            s for s, r in source_results.items()
            if r.success and r.evidence
        ]
        has_web = SourceType.WEB in sources_used
        has_rag = SourceType.RAG in sources_used
        has_tool = SourceType.TOOL in sources_used

        # If we have products from v6 pipeline, use their confidence
        v6_confidence = 0.0
        if existing_products:
            v6_confidence = sum(
                p.get("confidence", 0) for p in existing_products
            ) / max(len(existing_products), 1)

        confidence_breakdown = compute_confidence_breakdown(
            sources_count=len(sources_used),
            has_web=has_web,
            has_rag=has_rag,
            has_tool=has_tool,
            authority="rag" if has_rag else "community" if has_web else "unknown",
        )

        # Blend v6 confidence with hybrid confidence
        if v6_confidence > 0 and confidence_breakdown["total"] > 0:
            overall_confidence = round((v6_confidence + confidence_breakdown["total"]) / 2, 1)
        elif v6_confidence > 0:
            overall_confidence = v6_confidence
        else:
            overall_confidence = confidence_breakdown["total"]

        # ── Step 7: Determine confidence level ──
        if overall_confidence >= 70:
            conf_level = ConfidenceLevel.HIGH
        elif overall_confidence >= 40:
            conf_level = ConfidenceLevel.MEDIUM
        else:
            conf_level = ConfidenceLevel.LOW

        # ── Step 8: Build answer (or use LLM to synthesize) ──
        answer_text = ""
        citations = []

        if llm_call_fn and (all_evidence or existing_products):
            # Use LLM to synthesize answer from all sources
            try:
                evidence_text = "\n\n---\n\n".join(
                    f"[来源: {ev.source.value}] {ev.content[:400]}"
                    for ev in all_evidence[:8]
                )
                if existing_products:
                    product_text = "\n".join(
                        f"- {p.get('name','?')} | {p.get('platform','?')} | "
                        f"¥{p.get('price',0)} | 来源:{p.get('source','?')}"
                        for p in existing_products[:5]
                    )
                    evidence_text = f"已找到商品:\n{product_text}\n\n---\n\n{evidence_text}"

                system_prompt = (
                    "你是EVA Hybrid AI购物助手。请基于以下多源信息回答用户问题。\n"
                    "规则：\n"
                    "1. 只使用下方提供的信息，不要凭记忆补充数据\n"
                    "2. 如实标注每个数据的来源（标注为 [来源: xxx]）\n"
                    "3. 如果信息冲突，采用Web > RAG > Memory优先级\n"
                    "4. 如数据不足，诚实告知而非编造\n"
                    "5. 用中文回复，结构清晰\n"
                )

                answer_text, _, _ = await llm_call_fn(
                    system_prompt=system_prompt,
                    user_message=f"用户问题: {user_query}\n\n多源信息:\n{evidence_text}",
                    max_tokens=600,
                    temperature=0.3,
                    user_id=user_id,
                    node_name="hybrid_synthesize",
                )
            except Exception as e:
                append_log("ERROR", f"HybridAI LLM synthesis failed: {str(e)[:80]}")
                answer_text = self._build_fallback_answer(
                    user_query, all_evidence, existing_products,
                )
        elif existing_products:
            answer_text = self._build_product_answer(existing_products, all_evidence)
        elif all_evidence:
            answer_text = self._build_evidence_answer(all_evidence)
        else:
            answer_text = "当前系统无法从 RAG / Memory / Web 获取可靠信息。"

        # Build citations from evidence
        for ev in all_evidence[:5]:
            source_label = {
                SourceType.WEB: "Web搜索",
                SourceType.RAG: "知识库",
                SourceType.MEMORY: "历史记忆",
                SourceType.TOOL: "数据工具",
            }.get(ev.source, ev.source.value)

            content_preview = ev.content[:80].replace("\n", " ")
            citations.append(f"[{source_label}] {content_preview}...")

        # Add v6 product citations
        if existing_products:
            for p in existing_products[:3]:
                citations.append(
                    f"[商品搜索] {p.get('name','?')} "
                    f"({p.get('platform','?')}, ¥{p.get('price',0)})"
                )

        # ── Step 9: Hallucination check ──
        guard_result = check_hallucination(
            answer_text, all_evidence, products=existing_products,
        )

        # ── Step 10: Build warnings ──
        warnings = list(guard_result.warnings)
        if conflict_notes:
            warnings.extend(conflict_notes)
        if escalated:
            warnings.append("信息已升级查询至备用来源（首次来源返回结果不足）。")

        # ── Step 11: Assemble result ──
        total_ms = (time.perf_counter() - t_start) * 1000

        result = HybridResult(
            answer=answer_text,
            answer_summary=answer_text[:150] if answer_text else "",
            sources_used=sources_used or [SourceType.REASONING],
            primary_source=sources_used[0] if sources_used else None,
            confidence=overall_confidence,
            confidence_level=conf_level,
            confidence_breakdown=confidence_breakdown,
            all_evidence=all_evidence,
            citations=citations,
            conflicts_detected=len(conflicts) > 0,
            conflict_details=conflict_notes,
            warnings=warnings,
            hallucination_checks_passed=guard_result.passed,
            question_type=plan.question_type,
            total_latency_ms=total_ms,
            escalated=escalated,
        )

        # ── Update stats ──
        for s in sources_used:
            key = f"{s.value}_hits"
            if key in self._source_stats:
                self._source_stats[key] += 1

        append_log(
            "SUCCESS",
            f"HybridAI done ({total_ms:.0f}ms): qtype={plan.question_type.value} "
            f"sources={[s.value for s in sources_used]} "
            f"confidence={overall_confidence:.0f}% "
            f"escalated={escalated} conflicts={len(conflicts)} "
            f"hallucination={'PASS' if guard_result.passed else 'FAIL'}"
        )

        return result

    # ═══════════════════════════════════════════════════════════════
    # Source query helpers
    # ═══════════════════════════════════════════════════════════════

    async def _query_rag(self, query: str, top_k: int = 5) -> SourceResult:
        """Query the RAG knowledge base."""
        t0 = time.perf_counter()
        try:
            from app.services.rag_service import search_knowledge
            docs = await search_knowledge(query, top_k=top_k)
            evidence = [
                SourceEvidence(
                    source=SourceType.RAG,
                    content=doc.get("content", "")[:500],
                    relevance_score=doc.get("score", 0.5),
                    freshness_days=None,
                    authority="rag",
                )
                for doc in docs
            ]
            return SourceResult(
                source=SourceType.RAG,
                success=len(evidence) > 0,
                evidence=evidence,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return SourceResult(
                source=SourceType.RAG,
                success=False,
                error=str(e)[:100],
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

    async def _query_memory(
        self,
        query: str,
        user_id: str,
        chat_history: list[dict] | None = None,
    ) -> SourceResult:
        """Query memory (short-term Redis + long-term MySQL)."""
        t0 = time.perf_counter()
        evidence = []

        # Short-term: check Redis session history
        if chat_history:
            recent = chat_history[-6:]
            relevant = [
                m for m in recent
                if any(kw in (m.get("content") or "") for kw in query[:20])
            ]
            if relevant:
                evidence.append(SourceEvidence(
                    source=SourceType.MEMORY,
                    content=f"最近对话记录 ({len(relevant)}条相关):\n" +
                            "\n".join(
                                f"[{m.get('role','?')}]: {(m.get('content') or '')[:100]}"
                                for m in relevant
                            ),
                    relevance_score=0.4,
                    authority="manual",
                ))

        # Long-term: check MySQL memory
        if user_id:
            try:
                from app.services.memory_service import query_memories
                from app.core.database import async_session
                async with async_session() as db:
                    memories = await query_memories(db, user_id, keyword=query[:30], limit=5)
                    if memories:
                        evidence.append(SourceEvidence(
                            source=SourceType.MEMORY,
                            content=f"长期记忆 ({len(memories)}条):\n" +
                                    "\n".join(
                                        f"- {m.key}: {str(m.value)[:100]}"
                                        for m in memories
                                    ),
                            relevance_score=0.3,
                            authority="manual",
                        ))
            except Exception:
                pass

        return SourceResult(
            source=SourceType.MEMORY,
            success=len(evidence) > 0,
            evidence=evidence,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    # ═══════════════════════════════════════════════════════════════
    # Answer builders (fallback when LLM unavailable)
    # ═══════════════════════════════════════════════════════════════

    def _build_product_answer(
        self,
        products: list[dict],
        evidence: list[SourceEvidence],
    ) -> str:
        """Build answer from product data (no LLM)."""
        lines = [f"找到 {len(products)} 个相关商品：", ""]
        for i, p in enumerate(products[:8], 1):
            name = p.get("name", "未知")
            platform = p.get("platform", "未知")
            price = p.get("price", 0)
            src = p.get("source", "未知")
            conf = p.get("confidence", 0)
            lines.append(
                f"{i}. **{name}** — {platform} — "
                f"¥{price:,.0f}" +
                (f" [来源: {src}, 置信度: {conf:.0f}%]" if conf else "")
            )

        if evidence:
            lines.append("")
            lines.append("**补充信息（来自其他来源）：**")
            for ev in evidence[:3]:
                lines.append(f"- [{ev.source.value}] {ev.content[:150]}...")

        return "\n".join(lines)

    def _build_evidence_answer(self, evidence: list[SourceEvidence]) -> str:
        """Build answer from evidence only (no products, no LLM)."""
        lines = ["基于多源信息检索结果：", ""]
        for ev in evidence[:5]:
            source_label = {
                SourceType.WEB: "Web",
                SourceType.RAG: "知识库",
                SourceType.MEMORY: "记忆",
                SourceType.TOOL: "工具",
            }.get(ev.source, ev.source.value)
            lines.append(f"**[{source_label}]** {ev.content[:300]}")
            lines.append("")
        return "\n".join(lines)

    def _build_fallback_answer(
        self,
        query: str,
        evidence: list[SourceEvidence],
        products: list[dict] | None,
    ) -> str:
        """Build fallback answer when LLM is unavailable."""
        if products:
            return self._build_product_answer(products, evidence)
        if evidence:
            return self._build_evidence_answer(evidence)
        return format_insufficient_data()


# ═══════════════════════════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════════════════════════

hybrid_ai = HybridAI()
