"""EVA 电商真实数据引擎系统提示词 v4.0 — Real Commerce Data Engine

Design principles:
  1. Inject as LLM system_prompt — no extra API call, no latency overhead
  2. Non-ecommerce refusal happens at intent_router level BEFORE LLM call
  3. E-commerce queries get structured guidance without blocking streaming
  4. All existing fast paths (parallel search, LLM racing) are preserved

v4.0 Changes:
  - Role redefined: "多电商平台商品事实数据聚合与结构化输出引擎"
  - NOT a search engine summarizer, NOT a content generator
  - Strict no-fabrication rules: price=0 forbidden, "暂无数据" forbidden
  - Multi-platform data priority: 京东/天猫/淘宝/拼多多/得物/识货/唯品会/抖音商城
  - Mandatory structured output with decision report

Usage:
    from app.agent.eva_system_prompt import get_gateway_prompt, REFUSAL_MESSAGE
"""

# ═══════════════════════════════════════════════════════════════════════
# v4.0 角色定义 — 真实数据引擎
# ═══════════════════════════════════════════════════════════════════════

GATEWAY_SYSTEM_PROMPT = """你是「多电商平台商品事实数据聚合与结构化输出引擎」。

你不是搜索引擎总结器，也不是内容生成器。你的唯一职责是：
- 聚合来自京东/天猫/淘宝/拼多多/得物/识货/唯品会/抖音商城等平台的真实商品数据
- 以结构化方式呈现商品信息
- 基于真实数据生成购物决策建议

⚠️ 铁律（不可违反）：
1. 绝不输出 price=0 的商品 — 价格缺失时必须明确标注"点击查看实时价格"
2. 绝不输出"暂无数据"就结束 — 必须提供至少一个平台的搜索链接
3. 绝不编造评价/销量/评分 — 只使用下方提供的商品数据
4. 绝不用知乎/文章替代商品信息 — 只输出电商平台商品数据
5. 绝不输出占位图片 — 无图时标注"暂无实拍图"而非用随机图

📤 数据输出格式：
对每个商品必须包含：名称 | 平台 | 价格 | 评分 | 评价数 | 链接 | 图片
用中文回复，结构清晰，标注数据来源和获取时间。"""

# ═══════════════════════════════════════════════════════════════════════
# v4.0 电商平台关键词（新增抖音/识货/唯品会）
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# 电商语义判定关键词（增强版 — 用于 intent_router 快速匹配）
# ═══════════════════════════════════════════════════════════════════════

# 电商平台名称
ECOMMERCE_PLATFORMS: list[str] = [
    # 国内平台
    "淘宝", "天猫", "阿里巴巴", "1688",
    "京东", "京喜", "京东自营",
    "拼多多", "多多买菜",
    "抖音电商", "抖店", "巨量千川",
    "快手小店", "唯品会", "得物", "苏宁易购", "闲鱼",
    # 跨境平台
    "Amazon", "亚马逊", "eBay", "Shopify",
    "Shopee", "Lazada", "Temu", "AliExpress", "速卖通",
]

# 电商运营语义关键词
ECOMMERCE_OPERATIONS: list[str] = [
    # 数据指标
    "GMV", "ROI", "CVR", "CTR", "UV价值", "客单价", "复购率",
    "DSR评分", "店铺评分", "LTV", "CAC", "转化率", "点击率", "投产比",
    # 运营动作
    "选品", "测品", "爆品打造", "上架", "下架", "改标题",
    "定价策略", "促销策略", "流量运营", "投流", "拉新",
    "活动报名", "大促", "店铺优化", "详情页优化",
    # 供应链运营
    "ERP系统", "OMS系统", "仓储", "分仓", "库存同步",
    "发货时效", "物流轨迹", "揽收", "签收", "售后链路", "逆向物流",
]

# 投放与广告语义
ECOMMERCE_ADS: list[str] = [
    "直通车", "超级推荐", "DOU+", "信息流广告", "搜索广告",
    "广告投放", "ROI优化", "千川起量", "付费流量", "钻展",
    "淘客", "京准通", "快车", "万相台",
]

# 隐式电商语义（关键 — 无平台名但有交易意图）
IMPLICIT_ECOMMERCE_PATTERNS: list[str] = [
    # 商品 + 价格
    "这个多少钱", "那个多少钱", "多少钱一个", "价格多少",
    "什么价", "报价", "价位", "什么价格", "怎么卖",
    # 商品 + 库存
    "有没有货", "还有货吗", "库存", "能不能买到", "哪里能买",
    "在哪买", "去哪买", "怎么样才能买到",
    # 消费决策
    "哪个更划算", "哪个便宜", "哪个性价比", "值得买吗",
    "推荐一下", "帮我推荐", "什么牌子好", "哪个牌子好",
    # 选品 / 利润
    "这个能赚钱吗", "好卖吗", "利润多少", "能赚多少",
    "好不好卖", "销量怎么样",
]

# 泛电商语义关键词
ECOMMERCE_GENERAL_KEYWORDS: list[str] = [
    # 商品与交易
    "商品", "产品", "货品", "物品", "SKU", "SPU",
    "价格", "售价", "标价", "成本", "进货价", "利润",
    "库存", "现货", "预售", "补货", "断货",
    "下单", "购买", "付款", "支付", "成交",
    "发货", "配送", "物流", "快递", "运单号",
    "退货", "退款", "售后", "换货", "赔付",
    # 消费意图
    "便宜", "划算", "折扣", "优惠", "促销", "秒杀",
    "降价", "最低价", "性价比", "必买", "值得买",
    # 推荐/对比
    "推荐", "对比", "比较", "哪个好", "哪款好",
    "区别", "差别", "差异", "选哪个",
]

# ═══════════════════════════════════════════════════════════════════════
# 非电商拒答协议
# ═══════════════════════════════════════════════════════════════════════

REFUSAL_MESSAGE = (
    "「限制提示：本接口仅支持电商垂直领域数据查询，"
    "您当前输入不在服务白名单内，请重新描述您的电商业务场景。」"
)

# 严格非电商关键词（触发拒答的唯一条件）
STRICT_NON_ECOMMERCE_KEYWORDS: list[str] = [
    "天气", "下雨", "温度", "气温",
    "游戏", "王者荣耀", "吃鸡", "原神", "LOL", "DOTA",
    "编程", "代码", "Python", "Java", "JavaScript", "写个",
    "数学", "计算", "方程", "公式",
    "新闻", "政治", "选举", "政府",
    "笑话", "故事", "段子", "冷笑话",
    "翻译", "英文怎么说",
    "你是谁", "你的名字", "谁开发的",
    "唱歌", "跳舞", "画画",
]

# ═══════════════════════════════════════════════════════════════════════
# Prompt builder — injects gateway rules into LLM system prompt
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# 输出风格定义
# ═══════════════════════════════════════════════════════════════════════

STYLE_PROMPTS: dict[str, str] = {
    "default": "",
    "formal": (
        "\n\n## 输出风格：正式专业\n"
        "- 使用客观、严谨的语言，避免口语化表达\n"
        "- 结构清晰，使用标题分段\n"
        "- 数据和价格必须精确标注来源\n"
        "- 结论明确，不模棱两可"
    ),
    "casual": (
        "\n\n## 输出风格：轻松口语化\n"
        "- 用朋友聊天的语气回复，可以适当使用表情符号\n"
        "- 简化技术术语，用通俗语言解释\n"
        "- 保持亲切感但不失专业性\n"
        "- 回复简洁，避免冗长"
    ),
    "json": (
        "\n\n## 输出风格：结构化 JSON\n"
        "- 所有商品信息使用 JSON 格式输出\n"
        "- 每个商品包含: name, price, platform, url, rating, pros, cons\n"
        "- 不要输出 markdown 标题或解释文字\n"
        "- JSON 外不要有任何其他内容"
    ),
    "bullet": (
        "\n\n## 输出风格：要点摘要\n"
        "- 用短句和要点符号（-）呈现信息\n"
        "- 每个要点不超过一行\n"
        "- 优先列出最重要的 3-5 个结论\n"
        "- 省略背景介绍，直接给结论"
    ),
    "story": (
        "\n\n## 输出风格：场景化推荐\n"
        "- 以生活场景切入，描述使用体验\n"
        "- 说明「适合什么样的人」而非仅列参数\n"
        "- 营造画面感，让用户想象拥有商品后的感受\n"
        "- 保留必要的价格和平台信息"
    ),
}


def get_style_prompt(style: str = "default") -> str:
    """获取输出风格后缀 prompt。

    Args:
        style: default / formal / casual / json / bullet / story
    """
    return STYLE_PROMPTS.get(style, "")


def get_gateway_prompt(intent_type: str = "shopping", style: str = "default") -> str:
    """Return the gateway system prompt merged with intent-specific guidance.

    The gateway prompt is merged with existing intent prompts to:
      1. Keep the structural output requirements
      2. Add e-commerce domain constraints
      3. Preserve the anti-hallucination rules

    Args:
        intent_type: The classified intent type (buy_product, price_check, etc.)
        style: Output style — default / formal / casual / json / bullet / story
    """
    # Intent-specific addendums (minimal — gateway prompt is the base)
    intent_addendums = {
        "buy_product": "\n当前任务：帮助用户找到最合适的商品并给出购买建议。",
        "price_check": "\n当前任务：提供准确的价格对比信息。突出不同平台的价格差异。",
        "compare_products": "\n当前任务：客观对比多个商品，从价格、性能、口碑等维度分析。",
        "recommend_products": "\n当前任务：根据用户需求精准推荐商品，说明推荐理由。",
        "product_review": "\n当前任务：基于知识库内容客观评价商品，不编造未经证实的评价。",
        "shopping_guide": "\n当前任务：帮助用户理解如何选购，讲解关键参数和选购技巧。",
        "trend_analysis": "\n当前任务：展示热门商品和流行趋势，说明推荐理由。",
        "knowledge_qa": "\n当前任务：回答商品知识问题，基于知识库内容给出准确解答。",
        "general_chat": "\n当前任务：友好回复用户，引导电商相关需求。",
    }

    addendum = intent_addendums.get(intent_type, "")
    style_addendum = get_style_prompt(style)
    return GATEWAY_SYSTEM_PROMPT + addendum + style_addendum


def is_strictly_non_ecommerce(query: str) -> bool:
    """Check if query is CLEARLY and STRICTLY non-ecommerce.

    ONLY returns True when the query has ZERO e-commerce signals AND
    matches explicit non-ecommerce patterns. This implements the
    "宁可误放行，不可误拒绝" principle.

    Returns:
        True only when the query is unambiguously non-ecommerce
    """
    q = query.lower().strip()

    # Step 1: Check for any e-commerce signal (if found → NOT non-ecommerce)
    # Platforms
    for kw in ECOMMERCE_PLATFORMS:
        if kw.lower() in q:
            return False
    # Operations
    for kw in ECOMMERCE_OPERATIONS:
        if kw.lower() in q:
            return False
    # Ads
    for kw in ECOMMERCE_ADS:
        if kw.lower() in q:
            return False
    # General keywords
    for kw in ECOMMERCE_GENERAL_KEYWORDS:
        if kw.lower() in q:
            return False
    # Implicit patterns
    for pattern in IMPLICIT_ECOMMERCE_PATTERNS:
        if pattern in q:
            return False

    # Step 2: Check for explicit non-ecommerce keywords
    for kw in STRICT_NON_ECOMMERCE_KEYWORDS:
        if kw.lower() in q:
            return True

    # Step 3: If no e-commerce signal AND no non-ecommerce keyword → default to e-commerce
    return False
