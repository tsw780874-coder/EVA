"""Intent classification via fast keyword matching.

Previously this node made an LLM call (~1-3 s), but the keyword fallback
already covered every shopping scenario correctly.  Switching to pure
keyword classification eliminates one full LLM call from the critical
path and makes intent routing deterministic.
"""

from app.agent.state import AgentState

# Shopping intent keywords — covers Chinese & English queries
_SHOPPING_KEYWORDS = [
    # Chinese — purchase intent
    "价格", "比价", "对比", "最低价", "推荐", "哪个平台", "性价比",
    "便宜", "买", "多少钱", "哪里买", "哪家", "划算", "折扣", "优惠",
    "降价", "促销", "秒杀", "特价", "最低", "最便宜", "报价", "价位",
    "入手", "下单", "购买", "采购", "代购", "海淘", "网购",
    # Chinese — product categories
    "耳机", "手机", "笔记本", "平板", "相机", "手表", "键盘", "鼠标",
    "显示器", "显卡", "游戏机", "音箱", "电视", "家电", "家具", "床垫",
    "美妆", "护肤", "香水", "鞋", "包", "灯", "Switch", "PS5",
    # English
    "price", "compare", "cheap", "best", "buy", "deal", "discount",
    "shop", "purchase", "order", "recommend", "review", "rating",
    "lowest", "affordable", "worth", "vs", "versus",
]

_COMPLAINT_KEYWORDS = [
    "投诉", "维权", "退款", "退货", "假货", "质量问题", "差评",
    "客服", "欺骗", "上当", "坑", "投诉电话", "12315",
    "complaint", "refund", "return", "fake", "scam", "broken",
]

_PRODUCT_QUERY_KEYWORDS = [
    "参数", "规格", "配置", "尺寸", "重量", "材质", "功能",
    "续航", "待机", "存储", "内存", "处理器", "芯片", "像素",
    "spec", "specs", "specification", "warranty", "size", "weight",
]


async def intent_node(state: AgentState) -> dict:
    query = state.get("user_query", "")

    intent = _classify(query)

    return {
        "intent": intent,
        "messages": [{"role": "intent_agent", "content": f"意图分析: {intent}"}],
    }


def _classify(query: str) -> str:
    """Pure-keyword intent classification — zero latency, deterministic."""
    q = query.lower()

    if any(kw in q for kw in _SHOPPING_KEYWORDS):
        return "shopping"
    if any(kw in q for kw in _COMPLAINT_KEYWORDS):
        return "complaint"
    if any(kw in q for kw in _PRODUCT_QUERY_KEYWORDS):
        return "product_query"
    return "general"
