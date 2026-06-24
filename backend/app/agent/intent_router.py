"""Intent Router — 8-type intelligent intent classification and routing.

V2.0 replaces the simple shopping/general binary classifier with:
  buy_product      — User wants to purchase a specific product
  compare_products — User wants to compare multiple products
  recommend_products — User wants product recommendations
  product_review   — User wants reviews/ratings for a product
  shopping_guide   — User wants buying guidance (how to choose)
  price_check      — User wants price information only
  trend_analysis   — User wants trending/popular products
  knowledge_qa     — General product knowledge question

Each intent type routes to a different search/response strategy.

Usage:
    from app.agent.intent_router import route_intent, IntentType

    result = route_intent("iPhone16和小米16哪个好")
    # → IntentType.COMPARE_PRODUCTS, confidence=0.92
"""

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache


class IntentType(str, Enum):
    BUY_PRODUCT = "buy_product"
    COMPARE_PRODUCTS = "compare_products"
    RECOMMEND_PRODUCTS = "recommend_products"
    PRODUCT_REVIEW = "product_review"
    SHOPPING_GUIDE = "shopping_guide"
    PRICE_CHECK = "price_check"
    TREND_ANALYSIS = "trend_analysis"
    KNOWLEDGE_QA = "knowledge_qa"
    GENERAL_CHAT = "general_chat"


@dataclass
class IntentResult:
    intent: IntentType
    confidence: float
    matched_patterns: list[str] = field(default_factory=list)
    sub_intent: str = ""  # e.g., "single_product" vs "multi_product" for buy
    entities_found: int = 0  # Number of product entities detected


# ═══════════════════════════════════════════════════════════════════════
# Intent pattern definitions — ordered by priority
# ═══════════════════════════════════════════════════════════════════════

# Each pattern: (keywords/phrases, intent_type, weight)
# Higher weight = more specific match

_COMPARE_PATTERNS = [
    (["vs", "versus", "对比", "比较", "哪个好", "哪款好", "选哪个", "选哪款",
      "区别", "差别", "差异", "哪个更", "哪款更", "还是", "或者",
      "对比一下", "比较一下", "测评对比", "横评", "有什么区别"],
     IntentType.COMPARE_PRODUCTS, 0.90),
]

_RECOMMEND_PATTERNS = [
    (["推荐", "求推荐", "有什么推荐", "值得买", "值得入手", "必买",
      "性价比最高", "最好的", "哪个值得", "推荐一下", "求安利",
      "建议买", "应该买", "预算.*推荐", "帮我选"],
     IntentType.RECOMMEND_PRODUCTS, 0.85),
]

_PRICE_CHECK_PATTERNS = [
    (["多少钱", "价格", "报价", "最低价", "最便宜", "降价", "优惠",
      "折扣", "促销", "特价", "便宜", "划算", "跌了", "涨了",
      "价格走势", "什么时候便宜", "最低多少",
      # English
      "price", "cost", "cheap", "cheapest", "discount", "deal",
      "how much", "budget", "under", "affordable"],
     IntentType.PRICE_CHECK, 0.88),
]

_REVIEW_PATTERNS = [
    (["评价", "评测", "测评", "口碑", "怎么样", "好用吗", "值得吗",
      "质量", "耐用", "好不好", "使用体验", "优缺点", "开箱",
      "review", "体验", "测评视频", "实测",
      # English
      "rating", "best", "good", "quality", "worth"],
     IntentType.PRODUCT_REVIEW, 0.85),
]

_GUIDE_PATTERNS = [
    (["怎么选", "如何选", "怎么挑", "选购指南", "购买指南", "选购攻略",
      "新手入门", "小白怎么", "第一次买", "怎么判断", "注意事项",
      "选购建议", "怎么辨别", "避坑", "踩坑", "选购技巧",
      "如何购买", "指南", "攻略", "怎么区分",
      # English
      "how to choose", "guide", "which one", "what to look for"],
     IntentType.SHOPPING_GUIDE, 0.87),
]

_TREND_PATTERNS = [
    (["热门", "流行", "趋势", "最近火", "大家都在买", "潮流",
      "今年流行", "最新款", "新品", "刚发布", "刚出", "新上市",
      "trending", "热卖", "爆款", "销量最高", "排行榜", "排名",
      "top", "TOP", "热门.*推荐"],
     IntentType.TREND_ANALYSIS, 0.88),
]

_KNOWLEDGE_PATTERNS = [
    (["什么是", "是什么", "什么意思", "含义", "定义", "解释",
      "区别是什么", "属于什么", "材质", "工艺", "技术",
      "原理", "规格", "参数", "配置", "性能",
      "支持.*吗", "能用.*吗", "兼容"],
     IntentType.KNOWLEDGE_QA, 0.82),
]

_BUY_PATTERNS = [
    (["买", "购买", "下单", "入手", "采购", "代购", "海淘", "网购",
      "我要", "想买", "要买", "帮我找", "搜索", "找一下",
      "帮我看看", "有没有", "在哪买", "哪里买", "去哪买",
      "想入手", "搞一个", "来一个",
      # English patterns
      "buy", "purchase", "order", "shop", "i want", "i need",
      "find me", "looking for", "search for", "where to buy",
      "where can i", "i'd like", "get me"],
     IntentType.BUY_PRODUCT, 0.80),
]

# All patterns in priority order (most specific first)
_ALL_PATTERNS = (
    _COMPARE_PATTERNS + _RECOMMEND_PATTERNS + _PRICE_CHECK_PATTERNS +
    _REVIEW_PATTERNS + _GUIDE_PATTERNS + _TREND_PATTERNS +
    _KNOWLEDGE_PATTERNS + _BUY_PATTERNS
)


# ═══════════════════════════════════════════════════════════════════════
# Product entity keyword check
# ═══════════════════════════════════════════════════════════════════════

_PRODUCT_INDICATORS = [
    # Electronics
    "iPhone", "iPad", "MacBook", "AirPods", "Apple Watch", "华为", "小米", "三星",
    "Galaxy", "OPPO", "vivo", "荣耀", "一加", "ThinkPad", "ROG", "XPS",
    "RTX", "GeForce", "Radeon", "Ryzen", "Intel", "PlayStation", "Xbox",
    "Switch", "Nintendo", "Sony", "Bose", "Sennheiser", "DJI", "Dyson",
    "手机", "笔记本", "平板", "耳机", "手表", "键盘", "鼠标", "显示器",
    "显卡", "CPU", "游戏机", "音箱", "电视", "相机",
    # English product terms
    "phone", "laptop", "tablet", "headphone", "earphone", "keyboard", "mouse",
    "monitor", "gpu", "speaker", "camera", "watch", "console", "drone",
    # Sports
    "YONEX", "尤尼克斯", "Victor", "李宁", "Li-Ning", "川崎", "美津浓",
    "天斧", "疾光", "弓箭", "双刃", "龙牙", "雷霆", "神速", "羽毛球拍",
    "Nike", "Adidas", "AJ", "Air Jordan", "Dunk", "Air Force",
    # Categories
    "空调", "冰箱", "洗衣机", "扫地", "吸尘器", "床垫", "沙发",
    "美妆", "护肤", "香水", "精华", "面霜",
]


def _count_product_entities(query: str) -> int:
    """Count how many product indicators appear in the query."""
    q = query.lower()
    return sum(1 for indicator in _PRODUCT_INDICATORS if indicator.lower() in q)


# ═══════════════════════════════════════════════════════════════════════
# Intent classification logic
# ═══════════════════════════════════════════════════════════════════════

def _match_patterns(query: str) -> list[tuple[IntentType, float, str]]:
    """Match query against all intent patterns. Returns (intent, weight, matched_phrase)."""
    import re
    q = query.lower()
    matches: list[tuple[IntentType, float, str]] = []

    for patterns, intent, base_weight in _ALL_PATTERNS:
        for pattern in patterns:
            # Simple substring match (pattern is always a string)
            if pattern.lower() in q:
                matches.append((intent, base_weight, pattern))
                break

    return matches


@lru_cache(maxsize=512)
def route_intent(query: str) -> IntentResult:
    """Classify the user's intent into one of 8 types.

    Priority order (most specific wins):
      1. compare_products — explicit comparison keywords
      2. recommend_products — asking for recommendations
      3. price_check — asking about price
      4. product_review — asking about reviews/quality
      5. shopping_guide — asking how to choose
      6. trend_analysis — asking about trends/popularity
      7. knowledge_qa — asking product knowledge questions
      8. buy_product — explicit purchase intent
      9. general_chat — none of the above
    """
    q = query.lower().strip()
    entities = _count_product_entities(query)
    matches = _match_patterns(query)

    if not matches:
        # Check if query contains product names (fallback to buy_product)
        if entities > 0:
            return IntentResult(
                intent=IntentType.BUY_PRODUCT,
                confidence=0.65,
                matched_patterns=["product_entity_detected"],
                entities_found=entities,
            )
        # Check if it looks like a question
        if any(kw in q for kw in ["怎么", "如何", "为什么", "是什么", "什么", "哪个", "哪款"]):
            return IntentResult(
                intent=IntentType.SHOPPING_GUIDE,
                confidence=0.55,
                matched_patterns=["question_pattern"],
                entities_found=entities,
            )
        return IntentResult(
            intent=IntentType.GENERAL_CHAT,
            confidence=0.50,
            entities_found=entities,
        )

    # Sort by weight (highest first) — most specific match wins
    matches.sort(key=lambda x: x[1], reverse=True)
    best = matches[0]

    # Boost confidence if product entities are present
    confidence = best[1]
    if entities > 0:
        confidence = min(confidence + 0.05, 0.99)
    if entities > 1:
        confidence = min(confidence + 0.03, 0.99)

    return IntentResult(
        intent=best[0],
        confidence=confidence,
        matched_patterns=[m[2] for m in matches[:3]],
        entities_found=entities,
    )


# ═══════════════════════════════════════════════════════════════════════
# Intent-specific routing configuration
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class RouteConfig:
    """Configuration for how to handle each intent type."""
    enable_product_search: bool = True    # Search for products?
    enable_rag: bool = True               # Query RAG knowledge base?
    enable_live_search: bool = False       # Scrape e-commerce sites?
    enable_hot_products: bool = True       # Check hot products DB?
    enable_comparison: bool = False        # Generate comparison table?
    enable_guide: bool = False             # Generate buying guide?
    enable_trending: bool = False          # Include trending data?
    max_products: int = 5                  # Max products to return
    llm_temperature: float = 0.3           # LLM creativity level
    llm_max_tokens: int = 400              # LLM response length
    fast_mode: bool = False                # Skip slow operations?


INTENT_ROUTES: dict[IntentType, RouteConfig] = {
    IntentType.BUY_PRODUCT: RouteConfig(
        enable_product_search=True, enable_rag=True, enable_live_search=True,
        enable_hot_products=True, max_products=5, llm_temperature=0.3, llm_max_tokens=400,
    ),
    IntentType.COMPARE_PRODUCTS: RouteConfig(
        enable_product_search=True, enable_rag=True, enable_live_search=True,
        enable_hot_products=True, enable_comparison=True,
        max_products=6, llm_temperature=0.2, llm_max_tokens=600,
    ),
    IntentType.RECOMMEND_PRODUCTS: RouteConfig(
        enable_product_search=True, enable_rag=True, enable_live_search=True,
        enable_hot_products=True, enable_trending=True,
        max_products=8, llm_temperature=0.3, llm_max_tokens=500,
    ),
    IntentType.PRODUCT_REVIEW: RouteConfig(
        enable_product_search=False, enable_rag=True, enable_live_search=False,
        enable_hot_products=False, max_products=0, llm_temperature=0.3, llm_max_tokens=500,
    ),
    IntentType.SHOPPING_GUIDE: RouteConfig(
        enable_product_search=False, enable_rag=True, enable_live_search=False,
        enable_hot_products=False, enable_guide=True,
        max_products=3, llm_temperature=0.4, llm_max_tokens=600,
    ),
    IntentType.PRICE_CHECK: RouteConfig(
        enable_product_search=True, enable_rag=True, enable_live_search=True,
        enable_hot_products=True, max_products=5, llm_temperature=0.2, llm_max_tokens=350,
        fast_mode=True,
    ),
    IntentType.TREND_ANALYSIS: RouteConfig(
        enable_product_search=True, enable_rag=False, enable_live_search=False,
        enable_hot_products=True, enable_trending=True,
        max_products=10, llm_temperature=0.3, llm_max_tokens=500,
    ),
    IntentType.KNOWLEDGE_QA: RouteConfig(
        enable_product_search=False, enable_rag=True, enable_live_search=False,
        enable_hot_products=False, max_products=0, llm_temperature=0.3, llm_max_tokens=500,
    ),
    IntentType.GENERAL_CHAT: RouteConfig(
        enable_product_search=False, enable_rag=False, enable_live_search=False,
        enable_hot_products=False, max_products=0, llm_temperature=0.7, llm_max_tokens=300,
    ),
}


def get_route_config(intent_result: IntentResult) -> RouteConfig:
    """Get the routing configuration for a given intent."""
    return INTENT_ROUTES.get(intent_result.intent, INTENT_ROUTES[IntentType.GENERAL_CHAT])


def is_shopping_intent(intent_result: IntentResult) -> bool:
    """Check if the intent requires product search."""
    return intent_result.intent in (
        IntentType.BUY_PRODUCT, IntentType.COMPARE_PRODUCTS,
        IntentType.RECOMMEND_PRODUCTS, IntentType.PRICE_CHECK,
        IntentType.TREND_ANALYSIS,  # Trending also needs product data
    )


# ═══════════════════════════════════════════════════════════════════════
# Intent-specific prompts
# ═══════════════════════════════════════════════════════════════════════

INTENT_PROMPTS: dict[IntentType, str] = {
    IntentType.BUY_PRODUCT: (
        "你是电商购物专家。帮助用户找到最合适的商品。"
        "列出选项、价格、平台，给出购买建议。用中文回复。"
    ),
    IntentType.COMPARE_PRODUCTS: (
        "你是电商对比分析专家。将多个商品进行客观对比。"
        "从价格、性能、口碑、适用场景等维度比较。"
        "给出明确的推荐结论。用中文回复，可使用表格。"
    ),
    IntentType.RECOMMEND_PRODUCTS: (
        "你是电商推荐专家。根据用户需求精准推荐商品。"
        "了解用户预算、用途、偏好，给出Top-N推荐。"
        "每个推荐说明理由。用中文回复。"
    ),
    IntentType.PRODUCT_REVIEW: (
        "你是商品评测专家。基于知识库内容，客观评价商品。"
        "涵盖优缺点、使用体验、适合人群、注意事项。"
        "不要编造未经证实的评价。用中文回复。"
    ),
    IntentType.SHOPPING_GUIDE: (
        "你是购物指南专家。帮助用户理解如何选购某类商品。"
        "讲解关键参数、品牌差异、价格区间、选购技巧。"
        "给出实用的选购步骤和避坑建议。用中文回复。"
    ),
    IntentType.PRICE_CHECK: (
        "你是价格分析专家。提供准确的价格信息和比价建议。"
        "列出不同平台的价格，分析价格走势，给出最佳购买时机。"
        "用中文回复，突出价格信息。"
    ),
    IntentType.TREND_ANALYSIS: (
        "你是趋势分析专家。展示热门商品和流行趋势。"
        "基于热门商品库和热搜数据，推荐当下最值得关注的商品。"
        "说明每款商品为什么热门。用中文回复。"
    ),
    IntentType.KNOWLEDGE_QA: (
        "你是商品知识专家。回答用户关于商品的各类知识问题。"
        "基于知识库内容，给出准确、详细的解答。"
        "如果知识库中没有相关信息，诚实告知。用中文回复。"
    ),
    IntentType.GENERAL_CHAT: (
        "你是友好的AI购物助手。回答用户的一般性问题。"
        "如果涉及商品推荐，建议用户提供更具体的需求。用中文回复。"
    ),
}


def get_intent_prompt(intent_type: IntentType) -> str:
    """Get the LLM system prompt for a specific intent type."""
    return INTENT_PROMPTS.get(intent_type, INTENT_PROMPTS[IntentType.GENERAL_CHAT])
