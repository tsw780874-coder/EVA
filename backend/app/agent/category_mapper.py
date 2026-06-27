"""EVA Category Mapper v1.0 — 查询→类目映射引擎

核心功能：
  1. 将自然语言查询映射到商品类目体系
  2. 支持多平台类目名称（京东/天猫/拼多多/抖音/得物）
  3. 强制类目约束：用户搜西装 → 只允许返回男装类目
  4. 类目不匹配 → 过滤（防止跨类目污染）

原则：用户输入 = 同类目商品输出。宁可不返回，不返回错误的类目。

用法:
    from app.agent.category_mapper import map_category, CategoryConstraint

    constraint = map_category("我要买一件西装")
    # → CategoryConstraint(
    #     primary="menswear",
    #     subcategory="西服",
    #     platforms={"京东":"男装-西装", "天猫":"男装-西装", ...}
    #   )
"""

from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class CategoryConstraint:
    """类目约束 — 搜索结果必须满足此类目限制。"""
    primary: str           # 主类目: smartphone, menswear, shoes, etc.
    subcategory: str       # 子类目: 西服, 跑步鞋, 旗舰手机
    keywords: list[str]    # 类目关键词（用于产品名称/标签匹配）
    platforms: dict[str, str] = field(default_factory=dict)  # 平台→类目名
    confidence: float = 1.0  # 类目识别置信度

    @property
    def is_valid(self) -> bool:
        return bool(self.primary) and self.confidence > 0.3

    @property
    def all_keywords(self) -> list[str]:
        """返回所有类目匹配关键词（主类目+子类目+关键词）。"""
        kw = [self.primary, self.subcategory] + self.keywords
        return [k.lower() for k in kw if k]


# ═══════════════════════════════════════════════════════════════════════
# 完整类目体系 — 中文查询→英文主类目 + 子类目 + 多平台类目名
# ═══════════════════════════════════════════════════════════════════════

CATEGORY_MAP: dict[str, CategoryConstraint] = {
    # ── 男装 ──
    "西装": CategoryConstraint(
        primary="menswear", subcategory="西服/正装",
        keywords=["西装", "西服", "正装", "商务装", "套装", "西裤", "衬衫", "领带", "马甲"],
        platforms={"京东": "男装-西装", "天猫": "男装-西装", "拼多多": "服饰-正装", "抖音": "男装-西服"},
    ),
    "衬衫": CategoryConstraint(
        primary="menswear", subcategory="衬衫",
        keywords=["衬衫", "衬衣", "白衬衫", "条纹衬衫", "商务衬衫", "休闲衬衫"],
        platforms={"京东": "男装-衬衫", "天猫": "男装-衬衫", "拼多多": "服饰-衬衫"},
    ),
    "男装": CategoryConstraint(
        primary="menswear", subcategory="男装",
        keywords=["男装", "男衣", "男士", "男式", "男款", "男外套", "夹克", "风衣", "羽绒服男", "卫衣男"],
        platforms={"京东": "男装", "天猫": "男装", "拼多多": "服饰-男装", "抖音": "男装"},
    ),

    # ── 女装 ──
    "女装": CategoryConstraint(
        primary="womenswear", subcategory="女装",
        keywords=["女装", "女衣", "女士", "女式", "女款", "连衣裙", "裙子", "女外套", "女裤"],
        platforms={"京东": "女装", "天猫": "女装", "拼多多": "服饰-女装", "抖音": "女装"},
    ),
    "连衣裙": CategoryConstraint(
        primary="womenswear", subcategory="连衣裙",
        keywords=["连衣裙", "裙子", "长裙", "短裙", "半身裙", "礼服裙"],
        platforms={"京东": "女装-连衣裙", "天猫": "女装-连衣裙", "拼多多": "服饰-连衣裙"},
    ),

    # ── 鞋类 ──
    "运动鞋": CategoryConstraint(
        primary="shoes", subcategory="运动鞋",
        keywords=["运动鞋", "跑步鞋", "球鞋", "篮球鞋", "足球鞋", "训练鞋", "跑鞋", "sneaker"],
        platforms={"京东": "运动鞋", "天猫": "运动鞋", "得物": "运动鞋", "识货": "运动鞋"},
    ),
    "皮鞋": CategoryConstraint(
        primary="shoes", subcategory="皮鞋",
        keywords=["皮鞋", "正装鞋", "商务鞋", "德比鞋", "牛津鞋", "乐福鞋"],
        platforms={"京东": "男鞋-皮鞋", "天猫": "男鞋-皮鞋", "得物": "皮鞋"},
    ),

    # ── 3C 数码 ──
    "手机": CategoryConstraint(
        primary="smartphone", subcategory="手机",
        keywords=["手机", "iPhone", "华为手机", "小米手机", "三星手机", "OPPO", "vivo", "智能手机", "5G手机"],
        platforms={"京东": "手机", "天猫": "手机", "拼多多": "手机", "抖音": "手机"},
    ),
    "笔记本": CategoryConstraint(
        primary="laptop", subcategory="笔记本",
        keywords=["笔记本", "笔记本电脑", "MacBook", "ThinkPad", "游戏本", "轻薄本", "商务本", "laptop"],
        platforms={"京东": "电脑-笔记本", "天猫": "笔记本", "拼多多": "电脑-笔记本"},
    ),
    "平板": CategoryConstraint(
        primary="tablet", subcategory="平板电脑",
        keywords=["平板", "iPad", "平板电脑", "tablet", "学习平板"],
        platforms={"京东": "平板电脑", "天猫": "平板电脑", "拼多多": "平板电脑"},
    ),
    "耳机": CategoryConstraint(
        primary="headphone", subcategory="耳机",
        keywords=["耳机", "AirPods", "蓝牙耳机", "降噪耳机", "头戴耳机", "真无线", "TWS", "耳塞", "headphone"],
        platforms={"京东": "耳机", "天猫": "耳机", "拼多多": "耳机", "得物": "耳机"},
    ),
    "显卡": CategoryConstraint(
        primary="gpu", subcategory="显卡",
        keywords=["显卡", "RTX", "GeForce", "Radeon", "GPU", "独立显卡", "游戏显卡"],
        platforms={"京东": "电脑-显卡", "天猫": "显卡", "拼多多": "电脑-显卡"},
    ),
    "CPU": CategoryConstraint(
        primary="cpu", subcategory="处理器",
        keywords=["CPU", "处理器", "Intel", "AMD", "Ryzen", "酷睿", "i9", "i7", "i5"],
        platforms={"京东": "电脑-CPU", "天猫": "CPU", "拼多多": "电脑-CPU"},
    ),
    "显示器": CategoryConstraint(
        primary="monitor", subcategory="显示器",
        keywords=["显示器", "屏幕", "电竞显示器", "4K显示器", "monitor", "带鱼屏"],
        platforms={"京东": "显示器", "天猫": "显示器", "拼多多": "显示器"},
    ),

    # ── 家电 ──
    "空调": CategoryConstraint(
        primary="appliance", subcategory="空调",
        keywords=["空调", "挂机", "柜机", "变频空调", "中央空调", "格力", "美的空调"],
        platforms={"京东": "空调", "天猫": "空调", "拼多多": "家电-空调"},
    ),
    "冰箱": CategoryConstraint(
        primary="appliance", subcategory="冰箱",
        keywords=["冰箱", "冰柜", "对开门", "多门冰箱", "冷藏"],
        platforms={"京东": "冰箱", "天猫": "冰箱", "拼多多": "家电-冰箱"},
    ),
    "洗衣机": CategoryConstraint(
        primary="appliance", subcategory="洗衣机",
        keywords=["洗衣机", "烘干机", "洗烘一体", "滚筒", "波轮"],
        platforms={"京东": "洗衣机", "天猫": "洗衣机", "拼多多": "家电-洗衣机"},
    ),
    "扫地机": CategoryConstraint(
        primary="appliance", subcategory="扫地机器人",
        keywords=["扫地机", "扫地机器人", "吸尘器", "洗地机", "拖地机", "石头", "科沃斯", "追觅", "云鲸"],
        platforms={"京东": "扫地机器人", "天猫": "扫地机器人", "拼多多": "家电-清洁"},
    ),
    "电视": CategoryConstraint(
        primary="appliance", subcategory="电视",
        keywords=["电视", "电视机", "智能电视", "OLED", "QLED", "MiniLED", "激光电视"],
        platforms={"京东": "电视", "天猫": "电视", "拼多多": "家电-电视"},
    ),

    # ── 运动器材 ──
    "羽毛球拍": CategoryConstraint(
        primary="badminton", subcategory="羽毛球装备",
        keywords=["羽毛球", "羽毛球拍", "羽球拍", "YONEX", "尤尼克斯", "Victor", "李宁羽毛球", "川崎球拍", "天斧", "弓箭", "疾光", "双刃", "龙牙", "雷霆", "神速"],
        platforms={"京东": "羽毛球拍", "天猫": "羽毛球拍", "拼多多": "运动-羽毛球", "得物": "羽毛球拍"},
    ),

    # ── 美妆护肤 ──
    "美妆": CategoryConstraint(
        primary="beauty", subcategory="美妆护肤",
        keywords=["美妆", "化妆品", "口红", "粉底", "眼影", "腮红", "眉笔", "隔离", "卸妆"],
        platforms={"京东": "美妆", "天猫": "美妆", "拼多多": "美妆", "抖音": "美妆"},
    ),
    "护肤": CategoryConstraint(
        primary="skincare", subcategory="护肤",
        keywords=["护肤", "精华", "面霜", "乳液", "爽肤水", "面膜", "防晒", "眼霜", "洁面"],
        platforms={"京东": "护肤", "天猫": "护肤", "拼多多": "护肤", "抖音": "护肤"},
    ),
    "香水": CategoryConstraint(
        primary="fragrance", subcategory="香水",
        keywords=["香水", "perfume", "古龙水", "淡香水", "香氛", "Tom Ford", "Jo Malone"],
        platforms={"京东": "香水", "天猫": "香水", "得物": "香水"},
    ),

    # ── 箱包 ──
    "包": CategoryConstraint(
        primary="bags", subcategory="箱包",
        keywords=["包", "包包", "手提包", "双肩包", "背包", "斜挎包", "钱包", "公文包", "行李箱"],
        platforms={"京东": "箱包", "天猫": "箱包", "拼多多": "箱包", "得物": "箱包"},
    ),

    # ── 手表 ──
    "手表": CategoryConstraint(
        primary="watch", subcategory="手表",
        keywords=["手表", "腕表", "智能手表", "机械表", "Apple Watch", "卡西欧", "天梭", "劳力士"],
        platforms={"京东": "手表", "天猫": "手表", "得物": "手表", "拼多多": "手表"},
    ),

    # ── 家具 ──
    "床垫": CategoryConstraint(
        primary="furniture", subcategory="床垫",
        keywords=["床垫", "席梦思", "乳胶床垫", "弹簧床垫", "记忆棉"],
        platforms={"京东": "家具-床垫", "天猫": "床垫", "拼多多": "家具-床垫"},
    ),
    "沙发": CategoryConstraint(
        primary="furniture", subcategory="沙发",
        keywords=["沙发", "真皮沙发", "布艺沙发", "功能沙发", "懒人沙发"],
        platforms={"京东": "家具-沙发", "天猫": "沙发", "拼多多": "家具-沙发"},
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# Category mapping logic
# ═══════════════════════════════════════════════════════════════════════


@lru_cache(maxsize=512)
def map_category(query: str) -> CategoryConstraint:
    """将用户查询映射到商品类目。

    匹配策略（按优先级）：
      1. 精确关键词匹配（西装 → menswear/西服）
      2. 品牌名反推类目（YONEX → badminton）
      3. 商品名反推类目（iPhone → smartphone）
      4. 默认：无约束（允许所有类目）

    Returns:
        CategoryConstraint — 类目约束。如果 primary 为空，表示无约束。
    """
    q = query.lower().strip()

    # 1. 精确关键词匹配
    for keyword, constraint in CATEGORY_MAP.items():
        if keyword.lower() in q:
            return constraint

    # 2. 扩展关键词匹配（检查所有类目的所有关键词）
    best_match: CategoryConstraint | None = None
    best_len = 0
    for keyword, constraint in CATEGORY_MAP.items():
        for kw in constraint.keywords:
            if kw.lower() in q and len(kw) > best_len:
                best_match = constraint
                best_len = len(kw)

    if best_match:
        return best_match

    # 3. 品牌反推
    brand_to_category = {
        "yonex": "badminton", "尤尼克斯": "badminton", "victor": "badminton",
        "nike": "shoes", "adidas": "shoes", "aj": "shoes", "jordan": "shoes",
        "iphone": "smartphone", "ipad": "tablet", "macbook": "laptop", "airpods": "headphone",
        "apple": "smartphone", "华为": "smartphone", "小米": "smartphone", "三星": "smartphone",
        "nvidia": "gpu", "amd": "cpu", "intel": "cpu",
        "格力": "appliance", "美的": "appliance", "戴森": "appliance", "dyson": "appliance",
        "索尼": "headphone", "sony": "headphone", "bose": "headphone",
        "dell": "laptop", "联想": "laptop", "lenovo": "laptop", "thinkpad": "laptop",
        "tom ford": "fragrance", "la mer": "skincare", "海蓝之谜": "skincare",
    }
    for brand, cat_key in brand_to_category.items():
        if brand in q:
            if cat_key in CATEGORY_MAP:
                return CATEGORY_MAP[cat_key]
            # Find the category constraint for this category key
            for _, constraint in CATEGORY_MAP.items():
                if constraint.primary == cat_key:
                    return constraint

    # 4. 无约束（通用查询）- 返回空约束让所有类目通过
    return CategoryConstraint(
        primary="", subcategory="", keywords=[],
        confidence=0.0,
    )


# Platform search URL templates (shared with real_commerce_engine.py)
PLATFORM_SEARCH_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}&enc=utf-8",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "唯品会": "https://www.vip.com/search?keyword={}",
    "识货": "https://www.shihuo.cn/search?keyword={}",
    "抖音商城": "https://haohuo.jinritemai.com/views/search?keyword={}",
    "闲鱼": "https://s.2.taobao.com/list/list.htm?q={}",
    "苏宁易购": "https://search.suning.com/{}/",
}


def filter_by_category(
    products: list[dict],
    constraint: CategoryConstraint,
) -> tuple[list[dict], list[dict]]:
    """按类目约束过滤商品列表。

    匹配规则：
      1. 产品 category 字段精确匹配
      2. 产品 name/brand/model 包含类目关键词
      3. 如果 constraint 为空（无约束）→ 全部通过

    Returns:
        (matched, rejected) — 通过和未通过的商品列表
    """
    if not constraint.is_valid:
        return products, []

    matched = []
    rejected = []
    cat_keywords = constraint.all_keywords

    for p in products:
        product_cat = (p.get("category", "") or "").lower()
        product_name = (p.get("name", "") or "").lower()
        product_brand = (p.get("brand", "") or "").lower()
        product_model = (p.get("model", "") or "").lower()
        product_subcat = (p.get("subcategory", "") or "").lower()

        combined = f"{product_cat} {product_subcat} {product_name} {product_brand} {product_model}"

        # 检查是否匹配类目关键词
        matched_any = False
        for kw in cat_keywords:
            if kw in combined:
                matched_any = True
                break

        if matched_any:
            p["_category_match"] = True
            matched.append(p)
        else:
            p["_category_match"] = False
            p["_category_reject_reason"] = (
                f"类目不匹配: {p.get('category','?')} ∉ {constraint.primary}/{constraint.subcategory}"
            )
            rejected.append(p)

    return matched, rejected
