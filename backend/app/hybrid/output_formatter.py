"""Output Formatter — enforces the mandatory EVA response format.

Every response MUST follow this structure:
  【答案】
  ...
  【信息来源】
  - Web / RAG / Memory / Tool
  【置信度】
  High / Medium / Low

Usage:
    from app.hybrid.output_formatter import format_response

    formatted = format_response(hybrid_result)
"""

from app.hybrid.types import (
    HybridResult, ConfidenceLevel, SourceType,
)


def format_response(result: HybridResult) -> str:
    """Format a HybridResult into the mandatory EVA response format.

    Produces:
        【答案】
        <answer text>

        【信息来源】
        - Source1
        - Source2

        【置信度】
        High / Medium / Low
    """
    lines = []

    # ── Answer ──
    lines.append("【答案】")
    lines.append(result.answer or "当前系统无法从 RAG / Memory / Web 获取可靠信息。")
    lines.append("")

    # ── Conflicts (if any) ──
    if result.conflicts_detected and result.conflict_details:
        lines.append("### ⚡ 信息冲突")
        for detail in result.conflict_details:
            lines.append(f"- {detail}")
        lines.append("")

    # ── Warnings (if any) ──
    if result.warnings:
        for w in result.warnings:
            lines.append(f"> ⚠️ {w}")
        lines.append("")

    # ── Sources ──
    lines.append("【信息来源】")
    source_labels = {
        SourceType.WEB: "Web（实时搜索）",
        SourceType.RAG: "RAG（知识库检索）",
        SourceType.MEMORY: "Memory（历史记忆）",
        SourceType.TOOL: "Tool（数据库/API/计算）",
        SourceType.REASONING: "Reasoning（逻辑推理）",
    }
    for s in result.sources_used:
        label = source_labels.get(s, s.value)
        lines.append(f"- {label}")

    # Add citations if available
    if result.citations:
        lines.append("")
        for c in result.citations[:5]:
            lines.append(f"  · {c}")

    lines.append("")

    # ── Confidence ──
    lines.append("【置信度】")
    if result.confidence_level == ConfidenceLevel.HIGH:
        lines.append(f"High（{result.confidence:.0f}%）— 多源验证，数据可信")
    elif result.confidence_level == ConfidenceLevel.MEDIUM:
        lines.append(f"Medium（{result.confidence:.0f}%）— 单一来源或部分验证")
    else:
        lines.append(f"Low（{result.confidence:.0f}%）— 数据可信度较低，建议进一步确认")

    # Add breakdown if available
    if result.confidence_breakdown:
        bd = result.confidence_breakdown
        parts = []
        if bd.get("sources_score"):
            parts.append(f"来源数: {bd['sources_score']:.0f}")
        if bd.get("freshness_score"):
            parts.append(f"新鲜度: {bd['freshness_score']:.0f}")
        if bd.get("relevance_score"):
            parts.append(f"相关性: {bd['relevance_score']:.0f}")
        if bd.get("authority_score"):
            parts.append(f"权威度: {bd['authority_score']:.0f}")
        if parts:
            lines.append(f"（{' | '.join(parts)}）")

    lines.append("")

    # ── Hallucination note ──
    if not result.hallucination_checks_passed:
        lines.append("> ⚠️ **反幻觉检查**：本回答包含未经充分验证的内容，请谨慎参考。")
        lines.append("")

    return "\n".join(lines)


def format_quick_response(
    answer: str,
    sources: list[SourceType],
    confidence: float,
    confidence_level: ConfidenceLevel,
) -> str:
    """Lightweight formatter for quick responses (non-complex questions)."""
    result = HybridResult(
        answer=answer,
        sources_used=sources,
        confidence=confidence,
        confidence_level=confidence_level,
    )
    return format_response(result)


def format_insufficient_data() -> str:
    """Standard response when no reliable information is available."""
    return """【答案】
当前系统无法从 RAG / Memory / Web 获取可靠信息。建议：
1. 尝试使用不同的搜索关键词
2. 访问电商平台（京东、天猫、得物等）直接搜索
3. 提供更具体的商品名称或型号

【信息来源】
- 无可靠来源

【置信度】
Low — 信息不足，无法给出准确答案"""
