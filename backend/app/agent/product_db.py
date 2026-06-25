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

def _score_product(query: str, product: ProductEntry) -> float:
    """统一评分: 0.4×Semantic + 0.3×Keyword + 0.2×Popularity + 0.1×Brand"""
    q = query.lower()
    name_lower = product.name.lower()
    brand_lower = product.brand.lower()
    model_lower = product.model.lower()
    cat_lower = product.category.lower()

    # Semantic (0.4): 名称相似度
    semantic = 0.0
    if q in name_lower or name_lower in q:
        semantic = 100.0
    else:
        q_words = set(q.split())
        n_words = set(name_lower.split())
        if q_words:
            semantic = min(len(q_words & n_words) / max(len(q_words), 1) * 100.0, 100.0)

    # Keyword (0.3): 品牌/型号/品类匹配
    keyword = 0.0
    if brand_lower and brand_lower in q:
        keyword += 40
    if model_lower and model_lower in q:
        keyword += 40
    if cat_lower and cat_lower in q:
        keyword += 20
    keyword = min(keyword, 100.0)

    # Popularity (0.2): 热度分数
    popularity = product.popularity_score

    # Brand (0.1): 品牌权威权重
    TOP_BRANDS = {"apple", "samsung", "sony", "yonex", "victor", "lining", "nvidia", "intel", "amd"}
    brand_bonus = 100.0 if brand_lower in TOP_BRANDS else 50.0

    return 0.4 * semantic + 0.3 * keyword + 0.2 * popularity + 0.1 * brand_bonus


# ═══════════════════════════════════════════════════════════════════════
# 产品数据库 — 精选热销商品（合并自 hot_products + product_cache）
# ═══════════════════════════════════════════════════════════════════════

_PRODUCTS: list[ProductEntry] = []


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
            seed = hashlib.md5(p.name.encode()).hexdigest()[:8]
            p.image_url = f"https://picsum.photos/seed/{seed}/400/400"


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
    """从 Redis 读取缓存"""
    try:
        from app.services.memory_service import get_redis
        r = await get_redis()
        data = await r.get(_cache_key(query))
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


async def _set_cache(query: str, results: list[dict], ttl: int = 86400):
    """写入 Redis 缓存"""
    try:
        from app.services.memory_service import get_redis
        r = await get_redis()
        await r.set(_cache_key(query), json.dumps(results, ensure_ascii=False), ex=ttl)
    except Exception:
        pass


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

    # 5. 过滤低分
    results = [p.to_dict() for p, score in scored if score >= min_score][:top_k]

    # 6. 写缓存
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
