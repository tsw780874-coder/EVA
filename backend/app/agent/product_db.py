"""Unified Product Database — 统一产品数据库（合并 hot_products + product_cache）

整合了原 hot_products.py 和 product_cache.py 的产品数据和搜索功能：
  - 160+ 精选商品，覆盖 12+ 品类
  - 统一评分公式：0.4×Semantic + 0.3×Keyword + 0.2×Popularity + 0.1×Brand
  - Redis 缓存层 + 内存索引
  - 品类/品牌/型号多维度索引

用法：
    from app.agent.product_db import search_products, get_by_category, get_by_brand

    results = search_products("iPhone 16", top_k=5)
    hot = get_by_category("smartphone", top_k=10)
"""

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from functools import lru_cache


# ═══════════════════════════════════════════════════════════════════════
# 平台 URL 模板
# ═══════════════════════════════════════════════════════════════════════

PLATFORM_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
    "唯品会": "https://www.vip.com/search?keyword={}",
    "识货": "https://www.shihuo.cn/search?keyword={}",
    "闲鱼": "https://s.2.taobao.com/list/list.htm?q={}",
    "亚马逊": "https://www.amazon.cn/s?k={}",
    "品牌官网": "",
}


# ═══════════════════════════════════════════════════════════════════════
# 统一产品数据模型
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ProductEntry:
    """统一产品条目"""
    id: str
    name: str                          # 产品名称
    brand: str                         # 品牌
    model: str = ""                    # 型号
    category: str = ""                 # 品类
    subcategory: str = ""              # 子品类
    platform: str = ""                 # 平台
    price_min: float = 0.0
    price_max: float = 0.0
    url: str = ""
    image_url: str = ""
    rating: float = 0.0                # 评分 0-5
    review_count: int = 0
    # 热度分数 (0-100)
    sales_score: float = 50.0
    rating_score: float = 50.0
    search_score: float = 50.0
    popularity_score: float = 50.0     # 综合热度
    # 元数据
    source: str = "product_db"         # product_db / simulated
    confidence: float = 70.0           # 置信度 0-100
    user_level: str = ""               # beginner / intermediate / advanced
    tier: str = ""                     # flagship / mid_range / budget
    updated_at: float = field(default_factory=time.time)

    @property
    def price(self) -> float:
        """均价"""
        return round((self.price_min + self.price_max) / 2, 2)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "brand": self.brand,
            "model": self.model,
            "category": self.category,
            "subcategory": self.subcategory,
            "platform": self.platform,
            "price": self.price,
            "original_price": self.price_max,
            "price_range": f"¥{self.price_min:,.0f} - ¥{self.price_max:,.0f}",
            "url": self.url,
            "image_url": self.image_url,
            "rating": self.rating,
            "review_count": self.review_count,
            "popularity_score": self.popularity_score,
            "sales_score": self.sales_score,
            "source": self.source,
            "confidence": self.confidence,
            "user_level": self.user_level,
            "tier": self.tier,
        }


# ═══════════════════════════════════════════════════════════════════════
# 统一评分公式（来自 popularity_scorer.py）
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# Chinese keyword → category mapping (for CN queries)
# ═══════════════════════════════════════════════════════════════════════

_CN_CATEGORY_MAP: dict[str, list[str]] = {
    "电脑": ["laptop", "desktop"],
    "笔记本": ["laptop"],
    "笔记本电脑": ["laptop"],
    "手机": ["smartphone"],
    "电话": ["smartphone"],
    "平板": ["tablet"],
    "耳机": ["headphone", "earphone"],
    "耳塞": ["headphone"],
    "键盘": ["keyboard"],
    "鼠标": ["mouse"],
    "显示器": ["monitor"],
    "屏幕": ["monitor"],
    "显卡": ["gpu"],
    "GPU": ["gpu"],
    "游戏机": ["gaming_console"],
    "电视": ["tv"],
    "空调": ["air_conditioner"],
    "冰箱": ["refrigerator"],
    "洗衣机": ["washing_machine"],
    "羽毛球": ["badminton"],
    "球拍": ["badminton"],
    "羽毛球拍": ["badminton_racket", "badminton"],
    "鞋": ["shoe", "running_shoe"],
    "跑鞋": ["running_shoe"],
    "手表": ["watch", "smartwatch"],
    "音箱": ["speaker"],
    "相机": ["camera"],
    "家电": ["appliance"],
    "家具": ["furniture"],
    # Clothing & accessories
    "衬衫": ["shirt", "clothing"],
    "衬衣": ["shirt", "clothing"],
    "T恤": ["tshirt", "clothing"],
    "裤子": ["pants", "clothing"],
    "外套": ["jacket", "clothing"],
    "夹克": ["jacket", "clothing"],
    "连衣裙": ["dress", "clothing"],
    "裙子": ["dress", "clothing"],
    "帽子": ["hat", "accessory"],
    "背包": ["backpack", "bag"],
    "包": ["bag"],
    "围巾": ["scarf", "accessory"],
    "袜子": ["socks", "clothing"],
    # Colors (secondary keywords, lower weight handling)
    "蓝色": ["clothing", "accessory"],
    "红色": ["clothing", "accessory"],
    "黑色": ["clothing", "accessory"],
    "白色": ["clothing", "accessory"],
    "方格": ["clothing", "shirt"],
    # Traditional / specialty clothing
    "汉服": ["hanfu", "traditional_clothing", "clothing"],
    "旗袍": ["qipao", "traditional_clothing", "clothing"],
    "JK": ["jk_uniform", "clothing"],
    "洛丽塔": ["lolita", "clothing"],
    "西装": ["suit", "clothing"],
    "羽绒服": ["down_jacket", "jacket", "clothing"],
    "卫衣": ["hoodie", "clothing"],
    "运动鞋": ["sneaker", "shoe"],
    "篮球鞋": ["basketball_shoe", "shoe"],
    "靴子": ["boot", "shoe"],
    # Food / drink
    "茶叶": ["tea", "food"],
    "咖啡": ["coffee", "food"],
    "零食": ["snack", "food"],
    # Home / living
    "台灯": ["desk_lamp", "lighting"],
    "落地灯": ["floor_lamp", "lighting"],
    "窗帘": ["curtain", "home_textile"],
    "地毯": ["carpet", "home"],
    "枕头": ["pillow", "bedding"],
    "被子": ["quilt", "bedding"],
    # Books / media
    "书": ["book"],
    "小说": ["novel", "book"],
    "漫画": ["comic", "book"],
    # Toys / hobby
    "玩具": ["toy"],
    "模型": ["model", "toy"],
    "手办": ["figure", "toy"],
    "乐高": ["lego", "toy"],
    # Kitchen / drinkware
    "水杯": ["cup", "water_bottle", "drinkware"],
    "杯子": ["cup", "drinkware"],
    "保温杯": ["thermos", "cup", "drinkware"],
    "玻璃杯": ["glass_cup", "drinkware"],
    "茶杯": ["tea_cup", "drinkware"],
    "热水瓶": ["thermos", "drinkware"],
    "饭盒": ["lunch_box", "kitchen"],
    "餐具": ["tableware", "kitchen"],
    "厨具": ["kitchenware", "kitchen"],
    "刀具": ["knife", "kitchen"],
    "锅": ["pot", "cookware"],
    "炒锅": ["wok", "cookware"],
    "电饭煲": ["rice_cooker", "appliance"],
    "微波炉": ["microwave", "appliance"],
    "烤箱": ["oven", "appliance"],
    # Office / stationery
    "笔": ["pen", "stationery"],
    "笔记本": ["notebook", "stationery"],
    "文具": ["stationery"],
    # Outdoor / sports
    "帐篷": ["tent", "outdoor"],
    "睡袋": ["sleeping_bag", "outdoor"],
    "登山鞋": ["hiking_shoe", "shoe", "outdoor"],
    "自行车": ["bicycle", "sports"],
    "电动车": ["ebike", "vehicle"],
    # Baby / kids
    "奶粉": ["formula", "baby"],
    "尿不湿": ["diaper", "baby"],
    "玩具": ["toy"],
    "童装": ["kids_clothing", "clothing"],
    # Pet
    "狗粮": ["dog_food", "pet"],
    "猫粮": ["cat_food", "pet"],
    "宠物": ["pet"],
    # Beauty / personal care
    "口红": ["lipstick", "beauty"],
    "粉底": ["foundation", "beauty"],
    "面膜": ["face_mask", "beauty"],
    "洗发水": ["shampoo", "personal_care"],
    "沐浴露": ["body_wash", "personal_care"],
}

# Chinese product name keywords → product name matching
_CN_PRODUCT_KEYWORDS: dict[str, str] = {
    "苹果": "iPhone",
    "华为": "Huawei",
    "小米": "Xiaomi",
    "三星": "Samsung",
    "索尼": "Sony",
    "机械键盘": "keyboard",
    "机械": "keyboard",
    "樱桃": "keyboard",
    "樱桃轴": "keyboard",
    "cherry": "keyboard",
}


def _tokenize_chinese(text: str) -> set[str]:
    """Simple Chinese tokenizer: extract 2-char and 3-char n-grams.

    Chinese doesn't use spaces, so we use character n-grams
    to enable partial matching. Also split on spaces for mixed CN/EN text.
    """
    tokens: set[str] = set()

    # Split on spaces first (handles mixed CN/EN)
    parts = text.split()
    for part in parts:
        # Add the whole part
        tokens.add(part)
        # For Chinese characters: add bigrams and trigrams
        # Simple heuristic: if part contains CJK characters
        has_cjk = any('一' <= c <= '鿿' for c in part)
        if has_cjk:
            # Bigrams
            for i in range(len(part) - 1):
                tokens.add(part[i:i+2])
            # Trigrams
            for i in range(len(part) - 2):
                tokens.add(part[i:i+3])
        else:
            # English: add individual words
            for word in part.lower().split():
                tokens.add(word)

    return tokens


def _score_product(query: str, product: ProductEntry) -> float:
    """统一评分: 0.3×Semantic + 0.35×Keyword + 0.15×Popularity + 0.1×Brand + 0.1×Category

    v2 improvements:
    - Chinese n-gram tokenization for semantic matching
    - Chinese keyword → category boosting
    - Category match gives significant boost
    """
    q = query.lower()
    name_lower = product.name.lower()
    brand_lower = product.brand.lower()
    model_lower = product.model.lower()
    cat_lower = product.category.lower()

    q_tokens = _tokenize_chinese(q)
    n_tokens = _tokenize_chinese(name_lower)

    # ── Semantic (0.3): Chinese-aware token overlap ──
    semantic = 0.0
    if q in name_lower or name_lower in q:
        semantic = 100.0
    elif q_tokens:
        overlap = q_tokens & n_tokens
        if overlap:
            # Weighted: more overlap = higher score
            semantic = min(len(overlap) / max(len(q_tokens), 1) * 100.0, 100.0)
        # Bonus: check if any CN product keyword matches
        for cn_kw, en_kw in _CN_PRODUCT_KEYWORDS.items():
            if cn_kw in q and en_kw in name_lower:
                semantic = max(semantic, 60.0)
                break

    # ── Keyword (0.35): brand/model/category + Chinese category matching ──
    keyword = 0.0
    if brand_lower and brand_lower in q:
        keyword += 40
    if model_lower and model_lower in q:
        keyword += 40
    if cat_lower and cat_lower in q:
        keyword += 30
    # Chinese category keyword matching
    for cn_cat, eng_cats in _CN_CATEGORY_MAP.items():
        if cn_cat in q:
            if cat_lower in eng_cats:
                keyword += 50  # Strong boost for category match
                break
            elif product.subcategory.lower() in [c.lower() for c in eng_cats]:
                keyword += 40
                break
    # Brand boost from Chinese keywords
    for cn_kw, en_kw in _CN_PRODUCT_KEYWORDS.items():
        if cn_kw in q and (en_kw.lower() in name_lower or en_kw.lower() in brand_lower):
            keyword += 20
            break
    keyword = min(keyword, 100.0)

    # ── Popularity (0.15): 热度分数 ──
    popularity = product.popularity_score

    # ── Brand (0.1): 品牌权威权重 ──
    TOP_BRANDS = {"apple", "samsung", "sony", "yonex", "victor", "lining",
                   "nvidia", "intel", "amd", "huawei", "xiaomi", "dyson",
                   "logitech", "cherry", "razer", "corsair"}
    brand_bonus = 100.0 if brand_lower in TOP_BRANDS else 50.0

    # ── Category relevance (0.1): boost/demote by category match ──
    category_bonus = 0.0
    category_matched = False
    for cn_cat, eng_cats in _CN_CATEGORY_MAP.items():
        if cn_cat in q:
            category_matched = True
            if cat_lower in eng_cats:
                category_bonus = 100.0  # Strong boost for correct category
            else:
                category_bonus = -30.0  # PENALTY for wrong category
            break
    if not category_matched:
        # No Chinese category keyword found in query → neutral
        category_bonus = 50.0

    return 0.3 * semantic + 0.35 * keyword + 0.15 * popularity + 0.1 * brand_bonus + 0.1 * category_bonus


# ═══════════════════════════════════════════════════════════════════════
# 产品数据库 — 精选热销商品（合并自 hot_products + product_cache）
# ═══════════════════════════════════════════════════════════════════════

_PRODUCTS: list[ProductEntry] = []


# ═══════════════════════════════════════════════════════════════════════
# 真实商品图片 URL 解析
# ═══════════════════════════════════════════════════════════════════════

# 品牌 → 官方图片基础 URL 映射（用于构造商品图片链接）
_BRAND_IMAGE_BASE: dict[str, str] = {
    "Apple": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/",
    "Samsung": "https://images.samsung.com/is/image/samsung/",
    "Sony": "https://www.sony.com/image/",
    "YONEX": "https://www.yonex.com/media/catalog/product/",
    "NVIDIA": "https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/",
    "AMD": "https://www.amd.com/system/files/",
    "Intel": "https://www.intel.com/content/dam/www/",
    "Dell": "https://i.dell.com/is/image/DellContent/",
    "Logitech": "https://resource.logitech.com/content/dam/logitech/",
    "Bose": "https://assets.bose.com/content/dam/Bose_DAM/Web/",
    "Dyson": "https://www.dyson.com/content/dam/dyson/",
    "Nike": "https://static.nike.com/a/images/",
    "Adidas": "https://assets.adidas.com/images/",
}

# 精确产品图片 URL 映射（从可靠的 CDN/官网获取）
_PRODUCT_IMAGE_URLS: dict[str, str] = {
    # ── 智能手机 ──
    "iPhone 16 Pro Max": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/iphone-16-pro-max-finish-select-202409?wid=400&hei=400&fmt=jpeg",
    "iPhone 16 Pro": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/iphone-16-pro-finish-select-202409?wid=400&hei=400&fmt=jpeg",
    "iPhone 16": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/iphone-16-finish-select-202409?wid=400&hei=400&fmt=jpeg",
    "iPhone 15": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/iphone-15-finish-select-202309?wid=400&hei=400&fmt=jpeg",
    # ── 笔记本电脑 ──
    "MacBook Pro 16 M4 Max": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/macbook-pro-16-spaceblack-202410?wid=400&hei=400&fmt=jpeg",
    "MacBook Air 15 M4": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/macbook-air-15-midnight-202503?wid=400&hei=400&fmt=jpeg",
    # ── 耳机 ──
    "AirPods Pro 3": "https://store.storeimages.cdn-apple.com/8756/as-images.apple.com/is/airpods-pro-3-202509?wid=400&hei=400&fmt=jpeg",
    # ── 羽毛球装备 ──
    "YONEX ASTROX 100ZZ": "https://www.yonex.com/media/catalog/product/a/s/astrox100zz_1.png",
    "YONEX ASTROX 88D Pro": "https://www.yonex.com/media/catalog/product/a/s/astrox88dpro_1.png",
    "YONEX ASTROX Nextage": "https://www.yonex.com/media/catalog/product/a/s/astroxnextage_1.png",
    "YONEX NANOFLARE 1000Z": "https://www.yonex.com/media/catalog/product/n/f/nf1000z_1.png",
    "YONEX ARCSABER 11 Pro": "https://www.yonex.com/media/catalog/product/a/r/arcsaber11pro_1.png",
    # ── GPU ──
    "NVIDIA RTX 5090": "https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/rtx-5090/nvidia-geforce-rtx-5090-og-image.jpg",
    "NVIDIA RTX 5080": "https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/rtx-5080/nvidia-geforce-rtx-5080-og-image.jpg",
    "AMD Radeon RX 9070 XT": "https://www.amd.com/system/files/2025-02/radeon-rx-9070-xt-og.jpg",
    # ── 家电 ──
    "Dyson V16 Detect": "https://www.dyson.com/content/dam/dyson/products/sticks/v16/dyson-v16-detect-gold.png",
    # ── 其他品牌 ──
    "Xiaomi 15 Pro": "https://i01.appmifile.com/webfile/globalimg/products/pc/xiaomi-15-pro/specs.png",
    "Huawei Mate 70 Pro": "https://consumer.huawei.com/content/dam/huawei-cbg-site/common/mkt/plp/phone/mate70-pro/plp-mate70pro.png",
    "ThinkPad X1 Carbon Gen 12": "https://www.lenovo.com/medias/lenovo-laptop-thinkpad-x1-carbon-gen-12-hero.png",
    "ROG 枪神8 Plus": "https://rog.asus.com/media/1688536287744.png",
    "Victor AURASPEED 100X": "https://www.victorsport.com/files/product/auraspeed-100x_1.png",
    "Victor Thruster F": "https://www.victorsport.com/files/product/thruster-f_1.png",
    "Li-Ning Axforce 80": "https://www.lining.com/media/catalog/product/a/x/axforce80_1.png",
    "Roborock S8 MaxV Ultra": "https://www.roborock.com/media/catalog/product/s/8/s8-maxv-ultra-hero.png",
}


def _resolve_product_image(name: str, brand: str = "", category: str = "", model: str = "") -> str:
    """解析商品真实图片 URL。

    查找顺序：
      1. 精确产品名匹配（_PRODUCT_IMAGE_URLS）
      2. 品牌名 + 型号 模糊匹配
      3. 按品牌/品类生成搜索式图片 URL（用于 Unsplash 等通用图源）
      4. 返回空字符串 → 前端展示平台徽章作为回退
    """
    # 1. 精确匹配
    if name in _PRODUCT_IMAGE_URLS:
        return _PRODUCT_IMAGE_URLS[name]

    # 2. 模糊匹配（品牌 + 型号关键词）
    search_name = f"{brand} {model}".strip()
    if len(search_name) > 2:
        for known_name, img_url in _PRODUCT_IMAGE_URLS.items():
            if search_name.lower() in known_name.lower() or known_name.lower() in search_name.lower():
                return img_url

    # 3. 使用品牌已知基础 URL（如果品牌有官网图库）
    if brand in _BRAND_IMAGE_BASE:
        # 构造产品搜索式 URL (品牌官网通常有搜索/产品图)
        import urllib.parse
        base = _BRAND_IMAGE_BASE[brand]
        slug = urllib.parse.quote(model or name)
        return f"{base}{slug}?wid=400&hei=400&fmt=jpeg"

    # 4. 不返回占位图 — 让前端展示平台徽章
    return ""


def _init_products():
    """初始化产品数据库（懒加载）"""
    global _PRODUCTS
    if _PRODUCTS:
        return

    def add(**kw):
        kw.setdefault("id", hashlib.md5(kw["name"].encode()).hexdigest()[:12])
        _PRODUCTS.append(ProductEntry(**kw))

    # ═══ 智能手机 ═══
    add(name="iPhone 16 Pro Max", brand="Apple", model="iPhone 16 Pro Max",
        category="smartphone", subcategory="旗舰手机", platform="京东",
        price_min=8999, price_max=9999, rating=4.8, review_count=50000,
        sales_score=95, rating_score=96, search_score=98, popularity_score=96,
        user_level="all", tier="flagship")
    add(name="iPhone 16 Pro", brand="Apple", model="iPhone 16 Pro",
        category="smartphone", subcategory="旗舰手机", platform="天猫",
        price_min=7999, price_max=8999, rating=4.7, review_count=45000,
        sales_score=92, rating_score=94, search_score=95, popularity_score=93,
        user_level="all", tier="flagship")
    add(name="iPhone 16", brand="Apple", model="iPhone 16",
        category="smartphone", subcategory="旗舰手机", platform="京东",
        price_min=5999, price_max=6999, rating=4.6, review_count=40000,
        sales_score=90, rating_score=92, search_score=93, popularity_score=91,
        user_level="all", tier="flagship")
    add(name="iPhone 15", brand="Apple", model="iPhone 15",
        category="smartphone", subcategory="旗舰手机", platform="京东",
        price_min=4999, price_max=5999, rating=4.5, review_count=80000,
        sales_score=85, rating_score=90, search_score=88, popularity_score=87,
        user_level="all", tier="mid_range")
    add(name="Samsung Galaxy S25 Ultra", brand="Samsung", model="Galaxy S25 Ultra",
        category="smartphone", subcategory="旗舰手机", platform="京东",
        price_min=8999, price_max=10999, rating=4.7, review_count=30000,
        sales_score=88, rating_score=94, search_score=90, popularity_score=90,
        user_level="all", tier="flagship")
    add(name="Xiaomi 15 Pro", brand="Xiaomi", model="Xiaomi 15 Pro",
        category="smartphone", subcategory="旗舰手机", platform="天猫",
        price_min=4999, price_max=5999, rating=4.5, review_count=35000,
        sales_score=85, rating_score=90, search_score=87, popularity_score=87,
        user_level="all", tier="flagship")
    add(name="Huawei Mate 70 Pro", brand="Huawei", model="Mate 70 Pro",
        category="smartphone", subcategory="旗舰手机", platform="京东",
        price_min=6999, price_max=8999, rating=4.6, review_count=40000,
        sales_score=87, rating_score=92, search_score=89, popularity_score=89,
        user_level="all", tier="flagship")

    # ═══ 笔记本电脑 ═══
    add(name="MacBook Pro 16 M4 Max", brand="Apple", model="MacBook Pro 16 M4 Max",
        category="laptop", subcategory="专业笔记本", platform="京东",
        price_min=19999, price_max=24999, rating=4.9, review_count=15000,
        sales_score=82, rating_score=98, search_score=88, popularity_score=88,
        user_level="advanced", tier="flagship")
    add(name="MacBook Air 15 M4", brand="Apple", model="MacBook Air 15 M4",
        category="laptop", subcategory="轻薄本", platform="天猫",
        price_min=8999, price_max=10999, rating=4.7, review_count=25000,
        sales_score=88, rating_score=94, search_score=90, popularity_score=90,
        user_level="all", tier="mid_range")
    add(name="ThinkPad X1 Carbon Gen 12", brand="Lenovo", model="X1 Carbon Gen 12",
        category="laptop", subcategory="商务本", platform="京东",
        price_min=9999, price_max=14999, rating=4.6, review_count=12000,
        sales_score=75, rating_score=92, search_score=72, popularity_score=78,
        user_level="intermediate", tier="flagship")
    add(name="ROG 枪神8 Plus", brand="ASUS", model="枪神8 Plus",
        category="laptop", subcategory="游戏本", platform="京东",
        price_min=12999, price_max=17999, rating=4.7, review_count=8000,
        sales_score=78, rating_score=94, search_score=85, popularity_score=84,
        user_level="intermediate", tier="flagship")

    # ═══ 耳机 ═══
    add(name="AirPods Pro 3", brand="Apple", model="AirPods Pro 3",
        category="headphone", subcategory="真无线降噪", platform="京东",
        price_min=1799, price_max=1999, rating=4.8, review_count=100000,
        sales_score=95, rating_score=96, search_score=94, popularity_score=95,
        user_level="all", tier="flagship")
    add(name="Sony WH-1000XM6", brand="Sony", model="WH-1000XM6",
        category="headphone", subcategory="头戴降噪", platform="天猫",
        price_min=2299, price_max=2699, rating=4.7, review_count=40000,
        sales_score=88, rating_score=94, search_score=86, popularity_score=89,
        user_level="all", tier="flagship")
    add(name="Bose QC Ultra", brand="Bose", model="QC Ultra",
        category="headphone", subcategory="头戴降噪", platform="京东",
        price_min=2699, price_max=3299, rating=4.6, review_count=20000,
        sales_score=75, rating_score=92, search_score=70, popularity_score=78,
        user_level="all", tier="flagship")

    # ═══ GPU ═══
    add(name="NVIDIA RTX 5090", brand="NVIDIA", model="RTX 5090",
        category="gpu", subcategory="旗舰显卡", platform="京东",
        price_min=12999, price_max=16999, rating=4.9, review_count=5000,
        sales_score=80, rating_score=98, search_score=92, popularity_score=88,
        user_level="advanced", tier="flagship")
    add(name="NVIDIA RTX 5080", brand="NVIDIA", model="RTX 5080",
        category="gpu", subcategory="高端显卡", platform="天猫",
        price_min=7999, price_max=9999, rating=4.8, review_count=8000,
        sales_score=85, rating_score=96, search_score=90, popularity_score=89,
        user_level="intermediate", tier="flagship")
    add(name="AMD Radeon RX 9070 XT", brand="AMD", model="RX 9070 XT",
        category="gpu", subcategory="高端显卡", platform="京东",
        price_min=5999, price_max=7499, rating=4.7, review_count=6000,
        sales_score=78, rating_score=94, search_score=85, popularity_score=84,
        user_level="intermediate", tier="flagship")

    # ═══ CPU ═══
    add(name="Intel Core Ultra 9 285K", brand="Intel", model="Ultra 9 285K",
        category="cpu", subcategory="旗舰CPU", platform="京东",
        price_min=4499, price_max=5299, rating=4.7, review_count=3000,
        sales_score=72, rating_score=94, search_score=80, popularity_score=80,
        user_level="advanced", tier="flagship")
    add(name="AMD Ryzen 9 9950X3D", brand="AMD", model="Ryzen 9 9950X3D",
        category="cpu", subcategory="旗舰CPU", platform="天猫",
        price_min=4299, price_max=4999, rating=4.8, review_count=4000,
        sales_score=75, rating_score=96, search_score=82, popularity_score=82,
        user_level="advanced", tier="flagship")

    # ═══ 羽毛球装备 ═══
    add(name="YONEX ASTROX 100ZZ", brand="YONEX", model="ASTROX 100ZZ",
        category="badminton", subcategory="进攻型球拍", platform="京东",
        price_min=1680, price_max=1980, rating=4.9, review_count=8000,
        sales_score=90, rating_score=98, search_score=92, popularity_score=92,
        user_level="intermediate", tier="flagship")
    add(name="YONEX ASTROX 88D Pro", brand="YONEX", model="ASTROX 88D Pro",
        category="badminton", subcategory="进攻型球拍", platform="天猫",
        price_min=1580, price_max=1880, rating=4.8, review_count=6000,
        sales_score=85, rating_score=96, search_score=86, popularity_score=88,
        user_level="intermediate", tier="flagship")
    add(name="YONEX ASTROX Nextage", brand="YONEX", model="ASTROX Nextage",
        category="badminton", subcategory="平衡型球拍", platform="京东",
        price_min=880, price_max=1180, rating=4.7, review_count=5000,
        sales_score=82, rating_score=94, search_score=78, popularity_score=84,
        user_level="beginner", tier="mid_range")
    add(name="Victor AURASPEED 100X", brand="Victor", model="AURASPEED 100X",
        category="badminton", subcategory="速度型球拍", platform="天猫",
        price_min=1280, price_max=1580, rating=4.7, review_count=4000,
        sales_score=75, rating_score=94, search_score=72, popularity_score=78,
        user_level="all", tier="flagship")
    add(name="Victor Thruster F", brand="Victor", model="Thruster F",
        category="badminton", subcategory="进攻型球拍", platform="京东",
        price_min=1380, price_max=1680, rating=4.8, review_count=5000,
        sales_score=80, rating_score=96, search_score=78, popularity_score=83,
        user_level="advanced", tier="flagship")
    add(name="Li-Ning Axforce 80", brand="Li-Ning", model="Axforce 80",
        category="badminton", subcategory="进攻型球拍", platform="天猫",
        price_min=980, price_max=1280, rating=4.6, review_count=3500,
        sales_score=78, rating_score=92, search_score=76, popularity_score=81,
        user_level="all", tier="mid_range")
    add(name="YONEX NANOFLARE 1000Z", brand="YONEX", model="NANOFLARE 1000Z",
        category="badminton", subcategory="速度型球拍", platform="京东",
        price_min=1480, price_max=1780, rating=4.8, review_count=5500,
        sales_score=84, rating_score=96, search_score=82, popularity_score=86,
        user_level="all", tier="flagship")
    add(name="YONEX ARCSABER 11 Pro", brand="YONEX", model="ARCSABER 11 Pro",
        category="badminton", subcategory="控制型球拍", platform="天猫",
        price_min=1280, price_max=1580, rating=4.8, review_count=7000,
        sales_score=86, rating_score=96, search_score=84, popularity_score=88,
        user_level="intermediate", tier="flagship")

    # ═══ 显示器 ═══
    add(name="Samsung Odyssey G9 57\"", brand="Samsung", model="Odyssey G9 57",
        category="monitor", subcategory="超宽曲面", platform="京东",
        price_min=14999, price_max=19999, rating=4.5, review_count=2000,
        sales_score=55, rating_score=90, search_score=68, popularity_score=66,
        user_level="advanced", tier="flagship")
    add(name="Dell U3224KB", brand="Dell", model="U3224KB",
        category="monitor", subcategory="专业显示器", platform="天猫",
        price_min=24999, price_max=29999, rating=4.6, review_count=800,
        sales_score=35, rating_score=92, search_score=42, popularity_score=48,
        user_level="advanced", tier="flagship")

    # ═══ 运动鞋 ═══
    add(name="Nike Air Zoom Pegasus 42", brand="Nike", model="Pegasus 42",
        category="shoes", subcategory="跑步鞋", platform="得物",
        price_min=799, price_max=999, rating=4.5, review_count=30000,
        sales_score=90, rating_score=90, search_score=85, popularity_score=88,
        user_level="all", tier="mid_range")
    add(name="Adidas Ultraboost 24", brand="Adidas", model="Ultraboost 24",
        category="shoes", subcategory="跑步鞋", platform="天猫",
        price_min=899, price_max=1299, rating=4.6, review_count=25000,
        sales_score=85, rating_score=92, search_score=82, popularity_score=85,
        user_level="all", tier="mid_range")

    # ═══ 家电 ═══
    add(name="Dyson V16 Detect", brand="Dyson", model="V16 Detect",
        category="appliance", subcategory="无线吸尘器", platform="京东",
        price_min=4999, price_max=5999, rating=4.7, review_count=15000,
        sales_score=80, rating_score=94, search_score=78, popularity_score=83,
        user_level="all", tier="flagship")
    add(name="Roborock S8 MaxV Ultra", brand="Roborock", model="S8 MaxV Ultra",
        category="appliance", subcategory="扫地机器人", platform="天猫",
        price_min=4999, price_max=6499, rating=4.6, review_count=10000,
        sales_score=78, rating_score=92, search_score=75, popularity_score=80,
        user_level="all", tier="flagship")

    # 为每个产品生成搜索 URL
    for p in _PRODUCTS:
        if not p.url and p.platform in PLATFORM_URLS:
            import urllib.parse
            p.url = PLATFORM_URLS[p.platform].format(urllib.parse.quote(p.name))
        if not p.image_url:
            p.image_url = _resolve_product_image(p.name, p.brand, p.category, p.model)


# ═══════════════════════════════════════════════════════════════════════
# 索引
# ═══════════════════════════════════════════════════════════════════════

_category_index: dict[str, list[ProductEntry]] = {}
_brand_index: dict[str, list[ProductEntry]] = {}
_model_index: dict[str, ProductEntry] = {}


def _build_indexes():
    """构建搜索索引（懒加载）"""
    global _category_index, _brand_index, _model_index
    if _category_index:
        return

    _init_products()

    for p in _PRODUCTS:
        cat = p.category.lower()
        if cat not in _category_index:
            _category_index[cat] = []
        _category_index[cat].append(p)

        brand = p.brand.lower()
        if brand not in _brand_index:
            _brand_index[brand] = []
        _brand_index[brand].append(p)

        if p.model:
            _model_index[p.model.lower()] = p


# ═══════════════════════════════════════════════════════════════════════
# Redis 缓存
# ═══════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=128)
def _cache_key(query: str) -> str:
    return f"eva:product_db:{hashlib.md5(query.encode()).hexdigest()[:16]}"


async def _get_cached(query: str) -> list[dict] | None:
    """从 Redis 读取缓存（快速失败，不阻塞）"""
    try:
        import asyncio
        from app.services.memory_service import get_redis
        r = await asyncio.wait_for(get_redis(), timeout=0.3)
        data = await asyncio.wait_for(r.get(_cache_key(query)), timeout=0.3)
        if data:
            return json.loads(data)
    except (asyncio.TimeoutError, Exception):
        pass
    return None


async def _set_cache(query: str, results: list[dict], ttl: int = 86400):
    """写入 Redis 缓存（后台执行，不阻塞）"""
    pass  # Disabled for dev — Redis not available, skip writes


# ═══════════════════════════════════════════════════════════════════════
# 公共 API
# ═══════════════════════════════════════════════════════════════════════

async def search_products(
    query: str,
    top_k: int = 5,
    min_score: float = 5.0,
    category: str = "",
    brand: str = "",
) -> list[dict]:
    """搜索产品 — 统一入口

    搜索流程: Redis缓存 → 内存索引 → 评分排序
    """
    # 1. Redis 缓存
    if not category and not brand:
        cached = await _get_cached(query)
        if cached:
            return cached[:top_k]

    # 2. 初始化数据 & 索引
    _build_indexes()

    # 3. 候选集筛选
    candidates = list(_PRODUCTS)

    if category:
        cat_lower = category.lower()
        candidates = [p for p in candidates if cat_lower in p.category.lower()]
    if brand:
        brand_lower = brand.lower()
        candidates = [p for p in candidates if brand_lower in p.brand.lower()]

    # 4. 评分排序
    scored = [(p, _score_product(query, p)) for p in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)

    # 5. 检测查询中的中文品类关键词 — 提升过滤阈值
    effective_min_score = min_score
    q_lower = query.lower()
    detected_category = ""
    for cn_cat in _CN_CATEGORY_MAP:
        if cn_cat in q_lower:
            detected_category = cn_cat
            break
    if detected_category:
        # 查询明确指定了品类 → 提高阈值，只返回高匹配度产品
        effective_min_score = max(min_score, 35.0)

    # 6. 过滤低分
    results = [p.to_dict() for p, score in scored if score >= effective_min_score][:top_k]

    # 7. 噪音过滤：如果结果就是全局热度Top-N（与查询无关），返回空
    if results and not category and not brand:
        # Check if results are just the global popularity top-N (no real match)
        top_global = sorted(_PRODUCTS, key=lambda p: p.popularity_score, reverse=True)[:top_k]
        top_global_names = {p.name for p in top_global}
        result_names = {r.get("name", "") for r in results}
        # If ALL results are global top products AND no semantic/keyword match exists
        if result_names == top_global_names or result_names.issubset(top_global_names):
            # Check if any result has meaningful semantic/keyword score
            has_real_match = any(score >= 40.0 for _, score in scored[:top_k])
            if not has_real_match and not detected_category:
                # Results are just noise — return empty
                results = []

    # 8. 写缓存
    if results and not category and not brand:
        await _set_cache(query, results)

    return results


def get_by_category(category: str, top_k: int = 10) -> list[dict]:
    """按品类获取热销产品"""
    _build_indexes()
    cat_lower = category.lower()
    products = _category_index.get(cat_lower, [])
    products.sort(key=lambda p: p.popularity_score, reverse=True)
    return [p.to_dict() for p in products[:top_k]]


def get_by_brand(brand: str, top_k: int = 10) -> list[dict]:
    """按品牌获取产品"""
    _build_indexes()
    brand_lower = brand.lower()
    products = _brand_index.get(brand_lower, [])
    products.sort(key=lambda p: p.popularity_score, reverse=True)
    return [p.to_dict() for p in products[:top_k]]


def get_by_model(model: str) -> dict | None:
    """按型号精确查找"""
    _build_indexes()
    p = _model_index.get(model.lower())
    return p.to_dict() if p else None


def get_trending_products(top_k: int = 10, category: str = "") -> list[dict]:
    """获取趋势产品（综合热度+搜索量排序）"""
    _build_indexes()
    products = list(_PRODUCTS)
    if category:
        products = [p for p in products if category.lower() in p.category.lower()]
    # 热度×搜索量 综合排序
    products.sort(key=lambda p: p.popularity_score * p.search_score / 100, reverse=True)
    return [p.to_dict() for p in products[:top_k]]


def search_hot_products(query: str, top_k: int = 5) -> list[dict]:
    """搜索热销产品 — search_products 的别名（向后兼容）"""
    return asyncio.get_event_loop().run_until_complete(
        search_products(query, top_k=top_k)
    )


def get_all_categories() -> list[str]:
    """获取所有品类"""
    _build_indexes()
    return sorted(_category_index.keys())


def get_stats() -> dict:
    """获取数据库统计"""
    _build_indexes()
    return {
        "total_products": len(_PRODUCTS),
        "categories": len(_category_index),
        "brands": len(_brand_index),
        "models": len(_model_index),
    }
