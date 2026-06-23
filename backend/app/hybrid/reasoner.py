"""Multi-Step Reasoning Engine for EVA Hybrid AI.

Handles complex questions that require decomposition, sub-question
resolution, and synthesis of multiple information sources.

Architecture:
  1. Decompose complex question → sub-questions
  2. For each sub-question: identify needed sources
  3. Gather and verify information independently
  4. Synthesize sub-answers → final conclusion

Usage:
    from app.hybrid.reasoner import decompose_and_reason

    plan = decompose_and_reason("我应该买iPhone16还是等iPhone17?")
"""

from dataclasses import dataclass, field
from app.hybrid.types import SourceType


@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""
    step_id: int
    question: str                           # What this step tries to answer
    required_sources: list[SourceType]       # What sources are needed
    depends_on: list[int] = field(default_factory=list)  # Previous step IDs
    answer: str = ""                        # This step's conclusion
    confidence: float = 0.0                 # Confidence in this step
    sources_used: list[str] = field(default_factory=list)


@dataclass
class ReasoningPlan:
    """A complete multi-step reasoning plan."""
    original_question: str
    steps: list[ReasoningStep]
    final_conclusion: str = ""
    total_confidence: float = 0.0
    decomposition_strategy: str = ""       # How the question was decomposed


# ═══════════════════════════════════════════════════════════════════════
# Question decomposition strategies
# ═══════════════════════════════════════════════════════════════════════

_DECOMPOSITION_TEMPLATES = {
    "compare_products": {
        "description": "对比两个或多个商品的优劣",
        "sub_questions": [
            "各商品的核心参数与规格是什么？",
            "各商品在不同平台的价格是多少？",
            "各商品的用户评价和口碑如何？",
            "各商品的优缺点分别是什么？",
            "基于以上分析，哪个更适合？",
        ],
        "sources": [
            [SourceType.RAG, SourceType.WEB],
            [SourceType.WEB, SourceType.TOOL],
            [SourceType.RAG, SourceType.WEB],
            [SourceType.RAG, SourceType.WEB],
            [SourceType.REASONING],
        ],
    },
    "should_i_buy": {
        "description": "评估是否应该购买某个商品",
        "sub_questions": [
            "该商品当前的价格走势如何（涨还是跌）？",
            "该商品的核心参数和性能表现如何？",
            "该商品的用户口碑和主要投诉是什么？",
            "市场上是否有更好的替代选择？",
            "综合评估：当前是否值得购买？",
        ],
        "sources": [
            [SourceType.WEB, SourceType.TOOL],
            [SourceType.RAG, SourceType.WEB],
            [SourceType.RAG, SourceType.WEB],
            [SourceType.WEB, SourceType.RAG],
            [SourceType.REASONING],
        ],
    },
    "trend_analysis": {
        "description": "分析某个品类的趋势或热度",
        "sub_questions": [
            "当前热门品牌和型号有哪些？",
            "近期价格走势如何？",
            "热门商品的用户评价如何？",
            "未来趋势预测（基于近期动态）？",
        ],
        "sources": [
            [SourceType.WEB, SourceType.TOOL],
            [SourceType.WEB, SourceType.TOOL],
            [SourceType.RAG, SourceType.WEB],
            [SourceType.WEB, SourceType.REASONING],
        ],
    },
    "general_complex": {
        "description": "通用的复杂问题拆解",
        "sub_questions": [
            "问题的核心要素是什么？",
            "可以从哪些信息源获取相关数据？",
            "不同信息源之间的数据是否一致？",
            "综合结论是什么？",
        ],
        "sources": [
            [SourceType.RAG, SourceType.WEB, SourceType.MEMORY],
            [SourceType.TOOL, SourceType.WEB],
            [SourceType.REASONING],
            [SourceType.REASONING],
        ],
    },
}


def decompose_and_reason(query: str) -> ReasoningPlan:
    """Decompose a complex question into reasoning steps.

    Selects the best decomposition strategy based on query analysis,
    then builds a structured reasoning plan.

    Args:
        query: User's complex question

    Returns:
        ReasoningPlan with ordered steps and required sources.
    """
    q = query.lower()

    # Select decomposition strategy
    strategy_key = "general_complex"

    if any(kw in q for kw in ["对比", "比较", "哪个好", "vs", "区别"]):
        strategy_key = "compare_products"
    elif any(kw in q for kw in ["买", "入手", "值得", "应该买", "推荐买"]):
        strategy_key = "should_i_buy"
    elif any(kw in q for kw in ["热门", "趋势", "流行", "排行榜", "热度"]):
        strategy_key = "trend_analysis"

    template = _DECOMPOSITION_TEMPLATES[strategy_key]

    # Build reasoning steps
    steps = []
    for i, (sub_q, sources) in enumerate(
        zip(template["sub_questions"], template["sources"])
    ):
        deps = [i - 1] if i > 0 else []
        steps.append(ReasoningStep(
            step_id=i + 1,
            question=sub_q,
            required_sources=sources,
            depends_on=deps,
        ))

    return ReasoningPlan(
        original_question=query,
        steps=steps,
        decomposition_strategy=strategy_key,
    )


def synthesize_conclusions(
    plan: ReasoningPlan,
    sub_answers: dict[int, str],
    sub_confidences: dict[int, float],
) -> tuple[str, float]:
    """Synthesize sub-step answers into a final conclusion.

    Args:
        plan: The reasoning plan
        sub_answers: Mapping of step_id → answer text
        sub_confidences: Mapping of step_id → confidence (0-100)

    Returns:
        (final_conclusion, overall_confidence)
    """
    if not sub_answers:
        return "推理引擎无法得出有效结论（信息不足）。", 0.0

    # Build synthesis
    parts = []
    for step in plan.steps:
        if step.step_id in sub_answers:
            ans = sub_answers[step.step_id]
            if ans.strip():
                parts.append(f"**{step.question}**\n{ans}")

    conclusion = "\n\n".join(parts) if parts else "无法得出有效结论。"

    # Average confidence across steps
    confidences = [v for v in sub_confidences.values() if v > 0]
    avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    return conclusion, avg_conf
