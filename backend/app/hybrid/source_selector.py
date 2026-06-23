"""Source Selector — Step 1 of the Hybrid AI decision flow.

Analyzes the user's question and determines which information sources
to query, in what order, based on question type and content signals.

Priority: Web > RAG > Memory > Reasoning
"""

import re
from functools import lru_cache
from app.hybrid.types import (
    QuestionType, SourceType, SourcePlan,
)

# ═══════════════════════════════════════════════════════════════════════
# Question type signals — keyword-based classification (< 1ms)
# ═══════════════════════════════════════════════════════════════════════

_TIME_SENSITIVE_KEYWORDS = [
    "最新", "最近", "当前", "实时", "今天", "现在", "刚刚",
    "今日", "本周", "本月", "今年", "最新款", "刚发布", "新上市",
    "降价", "优惠", "促销", "秒杀", "限时", "活动",
    "latest", "current", "now", "today", "recent", "new",
]

_COMPUTATIONAL_KEYWORDS = [
    "计算", "换算", "多少", "总共", "合计", "对比价格",
    "统计", "分析数据", "查询", "数据库",
    "calculate", "compute", "how much", "total", "sum",
]

_HISTORICAL_KEYWORDS = [
    "上次", "之前", "历史", "回顾", "之前查过", "之前的对话",
    "上次搜索", "最近问过", "之前的", "我上次",
    "previous", "history", "last time", "before",
]

_COMPLEX_KEYWORDS = [
    "为什么", "如果", "是否应该", "建议", "综合考虑",
    "优缺点", "评估", "分析一下", "帮我决策",
    "why", "should i", "pros and cons", "analyze", "evaluate",
]

_PROCEDURAL_KEYWORDS = [
    "怎么", "如何", "步骤", "指南", "攻略", "教程",
    "怎样", "方法", "技巧", "注意事项", "流程",
    "how to", "guide", "tutorial", "steps", "procedure",
]

_COMPARATIVE_KEYWORDS = [
    "对比", "比较", "哪个好", "区别", "差异",
    "vs", "versus", "compare", "difference", "or",
]


def analyze_question(query: str) -> tuple[QuestionType, float]:
    """Analyze the question type and return with confidence.

    Returns:
        (QuestionType, confidence 0.0-1.0)
    """
    q = query.lower()

    scores: dict[QuestionType, float] = {}

    # Time-sensitive check (highest priority — forces web)
    time_matches = sum(1 for kw in _TIME_SENSITIVE_KEYWORDS if kw in q)
    if time_matches:
        scores[QuestionType.TIME_SENSITIVE] = min(0.7 + time_matches * 0.1, 1.0)

    # Computational check
    comp_matches = sum(1 for kw in _COMPUTATIONAL_KEYWORDS if kw in q)
    if comp_matches:
        scores[QuestionType.COMPUTATIONAL] = min(0.7 + comp_matches * 0.1, 1.0)

    # Historical check
    hist_matches = sum(1 for kw in _HISTORICAL_KEYWORDS if kw in q)
    if hist_matches:
        scores[QuestionType.HISTORICAL] = min(0.7 + hist_matches * 0.1, 1.0)

    # Complex check
    complex_matches = sum(1 for kw in _COMPLEX_KEYWORDS if kw in q)
    if complex_matches:
        scores[QuestionType.COMPLEX] = min(0.6 + complex_matches * 0.1, 1.0)

    # Procedural check
    proc_matches = sum(1 for kw in _PROCEDURAL_KEYWORDS if kw in q)
    if proc_matches:
        scores[QuestionType.PROCEDURAL] = min(0.7 + proc_matches * 0.1, 1.0)

    # Comparative check
    compa_matches = sum(1 for kw in _COMPARATIVE_KEYWORDS if kw in q)
    if compa_matches:
        scores[QuestionType.COMPARATIVE] = min(0.7 + compa_matches * 0.1, 1.0)

    # Default to FACTUAL if no strong signal
    if not scores:
        scores[QuestionType.FACTUAL] = 0.5

    # Return highest scoring type
    best_type = max(scores, key=scores.get)
    return best_type, scores[best_type]


@lru_cache(maxsize=512)
def select_sources(query: str) -> SourcePlan:
    """Select information sources based on question analysis.

    This implements Step 1-2 of the decision flow:
      1. Analyze question type
      2. Select information sources with priority

    Priority: Web > RAG > Memory > Reasoning
    """
    q_type, confidence = analyze_question(query)

    plan = SourcePlan(
        question_type=q_type,
        primary_sources=[],
        fallback_sources=[SourceType.REASONING],
        escalation_threshold=0.3,
    )

    # ── Configure sources per question type ──

    if q_type == QuestionType.TIME_SENSITIVE:
        # Web first, RAG as fallback
        plan.primary_sources = [SourceType.WEB]
        plan.fallback_sources = [SourceType.RAG, SourceType.TOOL]
        plan.requires_web = True

    elif q_type == QuestionType.COMPUTATIONAL:
        # Tool first, then Reasoning
        plan.primary_sources = [SourceType.TOOL]
        plan.fallback_sources = [SourceType.RAG, SourceType.WEB]
        plan.requires_tool = True

    elif q_type == QuestionType.HISTORICAL:
        # Memory first
        plan.primary_sources = [SourceType.MEMORY]
        plan.fallback_sources = [SourceType.RAG, SourceType.WEB]
        plan.requires_memory = True

    elif q_type == QuestionType.COMPLEX:
        # Multi-source with reasoning
        plan.primary_sources = [SourceType.RAG, SourceType.WEB, SourceType.TOOL]
        plan.fallback_sources = [SourceType.MEMORY]
        plan.requires_decomposition = True

    elif q_type == QuestionType.COMPARATIVE:
        # RAG + Web for multi-product comparison
        plan.primary_sources = [SourceType.RAG, SourceType.WEB]
        plan.fallback_sources = [SourceType.TOOL, SourceType.MEMORY]

    elif q_type == QuestionType.PROCEDURAL:
        # RAG for knowledge, Web as supplement
        plan.primary_sources = [SourceType.RAG]
        plan.fallback_sources = [SourceType.WEB, SourceType.MEMORY]

    else:  # FACTUAL
        # Balanced approach: RAG first, Web if needed
        plan.primary_sources = [SourceType.RAG]
        plan.fallback_sources = [SourceType.WEB, SourceType.TOOL, SourceType.MEMORY]

    # ── Boost: always check Web if time-keywords present ──
    q_lower = query.lower()
    if any(kw in q_lower for kw in _TIME_SENSITIVE_KEYWORDS):
        if SourceType.WEB not in plan.primary_sources:
            plan.primary_sources.insert(0, SourceType.WEB)
        plan.requires_web = True

    # ── Boost: always check Memory if historical signals ──
    if any(kw in q_lower for kw in _HISTORICAL_KEYWORDS):
        if SourceType.MEMORY not in plan.primary_sources:
            plan.primary_sources.insert(0, SourceType.MEMORY)
        plan.requires_memory = True

    return plan


def needs_escalation(
    results: dict[SourceType, list],  # source → evidence
    threshold: float = 0.3,
) -> bool:
    """Check if we need to escalate to fallback sources.

    Returns True if none of the primary sources returned high-quality results.
    """
    if not results:
        return True

    best_relevance = 0.0
    for evidence_list in results.values():
        for ev in evidence_list:
            if hasattr(ev, 'relevance_score'):
                best_relevance = max(best_relevance, ev.relevance_score)
            elif isinstance(ev, dict):
                best_relevance = max(best_relevance, ev.get('relevance_score', 0))

    return best_relevance < threshold
