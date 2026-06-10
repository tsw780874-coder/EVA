"""Smart query complexity classifier and model router.

Routes queries to the optimal LLM provider based on complexity:
  - Simple queries (chat, greetings, basic Q&A) → Groq LPU (~200-800ms)
  - Shopping queries (product comparison, analysis) → Groq first, DeepSeek fallback
  - Complex queries (multi-product deep analysis) → full racing pool

Complexity scoring: keyword + length + question-type heuristics.
Deterministic, zero latency (< 0.5ms).
"""

from dataclasses import dataclass, field
from functools import lru_cache

# ---------------------------------------------------------------------------
# Keyword sets for complexity scoring
# ---------------------------------------------------------------------------

SIMPLE_GREETINGS = {
    "你好", "hi", "hello", "hey", "早上好", "下午好", "晚上好",
    "谢谢", "thanks", "thank you", "再见", "bye", "拜拜",
    "在吗", "在不在", "ok", "好的",
}

SIMPLE_QUESTIONS = {
    "是什么", "什么是", "怎么用", "如何", "为什么", "能不能",
    "可以吗", "行吗", "怎么样", "多少钱", "在哪",
    "what is", "how to", "can you", "tell me",
}

COMPLEX_KEYWORDS = {
    "对比", "比较", "分析和", "综合分析", "深度", "报告",
    "详细", "全面", "所有平台", "全网", "各平台",
    "优缺点", "推荐理由", "购买建议", "性价比分析",
    "compare", "analysis", "detailed", "comprehensive",
    "all platforms", "best choice", "recommendation",
}

PRODUCT_COMPARISON = {
    "vs", "对比", "比较", "哪个好", "哪个划算", "哪个值得",
    "选哪个", "区别", "差异", "测评",
}

# ---------------------------------------------------------------------------
# Routing profiles
# ---------------------------------------------------------------------------


@dataclass
class RouteProfile:
    """Which providers to use, in priority order."""
    providers: list[str]
    max_tokens: int
    temperature: float
    timeout: float  # per-provider timeout in seconds
    description: str


# Fastest — Groq LPU only, low tokens, high temp for casual chat
SIMPLE_PROFILE = RouteProfile(
    providers=["groq", "glm_flash"],
    max_tokens=150,
    temperature=0.7,
    timeout=1.5,
    description="simple_chat",
)

# Balanced — Groq first, fast Chinese models, DeepSeek as safety net
SHOPPING_PROFILE = RouteProfile(
    providers=["groq", "glm_flash", "ernie_speed", "deepseek"],
    max_tokens=500,
    temperature=0.3,
    timeout=2.5,
    description="shopping_search",
)

# Deep — full racing pool for complex analysis, stricter temp for accuracy
COMPLEX_PROFILE = RouteProfile(
    providers=["groq", "deepseek", "glm47_flash", "openai"],
    max_tokens=600,
    temperature=0.2,
    timeout=3.5,
    description="complex_analysis",
)

# ---------------------------------------------------------------------------
# Complexity scoring
# ---------------------------------------------------------------------------


def _score_complexity(query: str) -> int:
    """Score 0-10 where 0=simplest, 10=most complex."""
    q = query.lower()
    score = 0

    # Length heuristic
    length = len(query)
    if length < 8:
        score -= 2
    elif length < 20:
        score += 0
    elif length < 60:
        score += 2
    elif length < 150:
        score += 4
    else:
        score += 6

    # Greetings → very simple
    if any(kw in q for kw in SIMPLE_GREETINGS) and length < 15:
        score -= 5

    # Complex indicators
    matches = sum(1 for kw in COMPLEX_KEYWORDS if kw in q)
    score += matches * 3

    # Product comparison → moderately complex
    matches = sum(1 for kw in PRODUCT_COMPARISON if kw in q)
    score += matches * 2

    # Simple questions → reduce complexity
    if any(kw in q for kw in SIMPLE_QUESTIONS) and length < 30:
        score -= 1

    return max(0, min(10, score))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1024)
def route_query(query: str, intent: str = "") -> RouteProfile:
    """Classify query complexity and return optimal RouteProfile.

    Args:
        query: User's input text
        intent: Intent classification (shopping/product_query/complaint/general)

    Returns:
        RouteProfile with provider list, token budget, and timeout.
    """
    complexity = _score_complexity(query)

    # General chat — simplest route
    if intent == "general" or (intent in ("", None) and complexity <= 2):
        return SIMPLE_PROFILE

    # Explicit complaint → simple profile (no shopping needed)
    if intent == "complaint":
        return SIMPLE_PROFILE

    # Shopping with low complexity → balanced
    if intent in ("shopping", "product_query"):
        if complexity <= 2:
            # Simple product question (e.g. "iPhone多少钱")
            return SIMPLE_PROFILE
        elif complexity <= 6:
            return SHOPPING_PROFILE
        else:
            return COMPLEX_PROFILE

    # Default: complexity-based
    if complexity <= 3:
        return SIMPLE_PROFILE
    elif complexity <= 7:
        return SHOPPING_PROFILE
    else:
        return COMPLEX_PROFILE


def get_fastest_profile() -> RouteProfile:
    """Ultra-minimal profile for when speed is the only concern."""
    return RouteProfile(
        providers=["groq"],
        max_tokens=100,
        temperature=0.8,
        timeout=1.0,
        description="fastest_chat",
    )
