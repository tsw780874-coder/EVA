"""Product Alias Database — canonical name resolution for all product categories.

Maps user-facing names (Chinese, abbreviations, slang) to canonical product names
with brand, model, and category metadata.

Usage:
    from app.agent.product_alias_db import resolve_product, get_category_constraint

    entity = resolve_product("天斧99Pro")
    # → ProductEntity(brand="YONEX", product="ASTROX 99 PRO", category="badminton_racket")
"""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass
class ProductEntity:
    """Structured product entity extracted from a query."""
    brand: str = ""              # Canonical brand name
    brand_aliases: list[str] = field(default_factory=list)  # All known brand names
    product: str = ""            # Canonical product/model name
    product_aliases: list[str] = field(default_factory=list)  # All known product names
    category: str = ""           # Product category
    subcategory: str = ""        # Sub-category (e.g., "racket", "shoe")
    confidence: float = 0.0      # Entity extraction confidence
    matched_alias: str = ""      # Which alias triggered the match

    @property
    def is_valid(self) -> bool:
        return bool(self.brand) or bool(self.product) or bool(self.category)

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "product": self.product,
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": self.confidence,
        }


# ═══════════════════════════════════════════════════════════════════════
# Category definitions — canonical categories for filtering
# ═══════════════════════════════════════════════════════════════════════

CATEGORY_HIERARCHY: dict[str, list[str]] = {
    "smartphone": ["手机", "智能手机", "5G手机", "折叠屏手机", " iPhone", "iphone"],
    "laptop": ["笔记本", "笔记本电脑", "游戏本", "轻薄本", "商务本", "laptop", "macbook"],
    "tablet": ["平板", "平板电脑", "ipad", "iPad", "tablet"],
    "headphone": ["耳机", "蓝牙耳机", "降噪耳机", "TWS耳机", "headphone", "airpods", "AirPods"],
    "smartwatch": ["手表", "智能手表", "smartwatch", "watch", "Apple Watch"],
    "graphics_card": ["显卡", "GPU", "独立显卡", "游戏显卡", "RTX", "rtx", "GeForce", "Radeon"],
    "cpu": ["CPU", "处理器", "cpu", "英特尔", "AMD", "Ryzen", "Core"],
    "monitor": ["显示器", "屏幕", "电竞显示器", "4K显示器", "monitor"],
    "gaming_console": ["游戏机", "主机", "PS5", "Switch", "Xbox", "PlayStation", "Nintendo"],
    "tv": ["电视", "电视机", "智能电视", "OLED电视", "TV"],
    "camera": ["相机", "微单", "单反", "运动相机", "camera", "DJI"],
    "keyboard": ["键盘", "机械键盘", "keyboard"],
    "mouse": ["鼠标", "游戏鼠标", "mouse"],
    "shoe": ["鞋", "运动鞋", "篮球鞋", "跑鞋", "sneaker", "AJ", "Dunk", "Air Force"],
    "skincare": ["护肤", "美妆", "精华", "面霜", "香水", "skincare", "beauty"],
    "home_appliance": ["家电", "空调", "冰箱", "洗衣机", "扫地", "吸尘器", "电视"],
    # === SPORTS EQUIPMENT ===
    "badminton_racket": [
        "羽毛球拍", "羽球拍", "球拍", "badminton", "racket",
        "天斧", "疾光", "弓箭", "纳米", "ASTROX", "NANOFLARE",
        "ARCSABER", "DUORA", "VOLTRIC", "NANORAY",
        "尤尼克斯", "YONEX", "yonex",
        "维克多", "胜利", "Victor", "victor",
        "李宁", "Li-Ning", "lining",
        "川崎", "Kawasaki",
        "美津浓", "Mizuno",
        "凯胜", "Kason",
    ],
    "badminton_shuttlecock": ["羽毛球", "羽球", "shuttlecock", "AS-", "AEROSENSA"],
    "badminton_shoe": ["羽毛球鞋", "羽球鞋", "badminton shoe"],
    "tennis_racket": ["网球拍", "tennis racket", "网球"],
    "basketball": ["篮球", "basketball"],
    "football": ["足球", "football"],
    "running_shoe": ["跑鞋", "跑步鞋", "running shoe"],
    "bicycle": ["自行车", "单车", "骑行", "bike", "bicycle"],
    "fitness": ["健身", "哑铃", "跑步机", "椭圆机", "fitness"],
}


# Reverse mapping: keyword → category
_KEYWORD_TO_CATEGORY: dict[str, str] = {}
for _cat, _keywords in CATEGORY_HIERARCHY.items():
    for _kw in _keywords:
        _kw_lower = _kw.lower()
        # Keep the most specific category for each keyword
        if _kw_lower not in _KEYWORD_TO_CATEGORY:
            _KEYWORD_TO_CATEGORY[_kw_lower] = _cat


# ═══════════════════════════════════════════════════════════════════════
# Brand database — canonical brand name + all aliases
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BrandInfo:
    canonical: str
    aliases: list[str]
    categories: list[str]  # Which categories this brand belongs to


BRAND_DB: dict[str, BrandInfo] = {}

def _register_brand(canonical: str, aliases: list[str], categories: list[str]):
    info = BrandInfo(canonical=canonical, aliases=aliases, categories=categories)
    BRAND_DB[canonical.lower()] = info
    for a in aliases:
        BRAND_DB[a.lower()] = info


# Electronics
_register_brand("Apple", ["apple", "苹果", "iPhone", "iPad", "MacBook", "AirPods"],
                ["smartphone", "laptop", "tablet", "headphone", "smartwatch"])
_register_brand("HUAWEI", ["huawei", "华为", "Mate", "Pura", "鸿蒙"],
                ["smartphone", "laptop", "tablet", "smartwatch", "headphone"])
_register_brand("Xiaomi", ["xiaomi", "小米", "Redmi", "红米", "POCO"],
                ["smartphone", "laptop", "tablet", "headphone", "smartwatch"])
_register_brand("Samsung", ["samsung", "三星", "Galaxy"],
                ["smartphone", "laptop", "tablet", "headphone", "smartwatch", "tv", "monitor"])
_register_brand("OPPO", ["oppo", "Find", "Reno"], ["smartphone", "headphone", "smartwatch"])
_register_brand("vivo", ["vivo", "X系列", "iQOO"], ["smartphone"])
_register_brand("Honor", ["honor", "荣耀", "Magic"], ["smartphone", "laptop", "tablet"])
_register_brand("OnePlus", ["oneplus", "一加"], ["smartphone"])
_register_brand("NVIDIA", ["nvidia", "英伟达", "GeForce", "RTX", "GTX"], ["graphics_card"])
_register_brand("AMD", ["amd", "Radeon", "Ryzen", "锐龙"], ["graphics_card", "cpu"])
_register_brand("Intel", ["intel", "英特尔", "Core", "酷睿"], ["cpu"])
_register_brand("Sony", ["sony", "索尼", "SONY", "Xperia", "PlayStation", "PS5"],
                ["smartphone", "headphone", "camera", "tv", "gaming_console"])
_register_brand("Nintendo", ["nintendo", "任天堂", "Switch"], ["gaming_console"])
_register_brand("Microsoft", ["microsoft", "微软", "Surface", "Xbox"], ["laptop", "tablet", "gaming_console"])
_register_brand("Lenovo", ["lenovo", "联想", "ThinkPad", "拯救者", "Legion", "Yoga", "小新"],
                ["laptop", "tablet"])
_register_brand("Dell", ["dell", "戴尔", "XPS", "Alienware"], ["laptop", "monitor"])
_register_brand("HP", ["hp", "惠普", "Spectre", "暗影精灵"], ["laptop"])
_register_brand("ASUS", ["asus", "华硕", "ROG"], ["laptop", "graphics_card", "monitor"])
_register_brand("Acer", ["acer", "宏碁"], ["laptop"])
_register_brand("Logitech", ["logitech", "罗技", "Logi"], ["mouse", "keyboard"])
_register_brand("Razer", ["razer", "雷蛇"], ["mouse", "keyboard", "headphone"])
_register_brand("Nike", ["nike", "耐克", "AJ", "Air Jordan", "Dunk", "Air Force"],
                ["shoe", "running_shoe"])
_register_brand("Adidas", ["adidas", "阿迪达斯", "阿迪", "Samba"], ["shoe", "running_shoe"])
_register_brand("DJI", ["dji", "大疆"], ["camera", "drone"])
_register_brand("Dyson", ["dyson", "戴森"], ["home_appliance"])
_register_brand("Bose", ["bose"], ["headphone"])
_register_brand("Sennheiser", ["sennheiser", "森海塞尔"], ["headphone"])
_register_brand("Gree", ["gree", "格力"], ["home_appliance"])
_register_brand("Midea", ["midea", "美的"], ["home_appliance"])
_register_brand("Haier", ["haier", "海尔"], ["home_appliance"])
_register_brand("Roborock", ["roborock", "石头"], ["home_appliance"])
_register_brand("Ecovacs", ["ecovacs", "科沃斯"], ["home_appliance"])

# === SPORTS BRANDS ===
_register_brand("YONEX", ["yonex", "尤尼克斯", "yy", "Yonex", "YONEX", "尤尼克斯Yonex"],
                ["badminton_racket", "badminton_shuttlecock", "badminton_shoe", "tennis_racket"])
_register_brand("Victor", ["victor", "维克多", "胜利", "Victor", "VICTOR"],
                ["badminton_racket", "badminton_shuttlecock", "badminton_shoe"])
_register_brand("Li-Ning", ["li-ning", "lining", "李宁", "LN", "Li-Ning"],
                ["badminton_racket", "badminton_shoe", "shoe", "running_shoe", "basketball"])
_register_brand("Kawasaki", ["kawasaki", "川崎"],
                ["badminton_racket"])
_register_brand("Mizuno", ["mizuno", "美津浓"],
                ["badminton_racket", "badminton_shoe", "running_shoe"])
_register_brand("Apacs", ["apacs", "雅拍"],
                ["badminton_racket"])
_register_brand("Kason", ["kason", "凯胜"],
                ["badminton_racket"])
_register_brand("Anta", ["anta", "安踏"], ["shoe", "running_shoe", "basketball"])
_register_brand("Xtep", ["xtep", "特步"], ["shoe", "running_shoe"])
_register_brand("361°", ["361", "361°", "361度"], ["shoe", "running_shoe"])


# ═══════════════════════════════════════════════════════════════════════
# Product/Model alias database — canonical model name resolution
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ModelInfo:
    canonical: str           # Canonical model name
    aliases: list[str]       # All known aliases
    brand: str               # Canonical brand
    category: str            # Product category
    subcategory: str = ""    # e.g., "racket", "shoe"


MODEL_DB: dict[str, ModelInfo] = {}

def _register_model(aliases: list[str], canonical: str, brand: str, category: str, subcategory: str = ""):
    info = ModelInfo(canonical=canonical, aliases=aliases, brand=brand, category=category, subcategory=subcategory)
    for a in aliases:
        MODEL_DB[a.lower()] = info
    MODEL_DB[canonical.lower()] = info


# === YONEX Badminton Rackets ===
_register_model(
    ["天斧99pro", "天斧99 pro", "天斧99", "99pro", "99 pro", "ax99pro", "ax99 pro", "ax99"],
    "ASTROX 99 PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["天斧100zz", "天斧100 zz", "天斧100", "100zz", "100 zz", "ax100zz", "ax100 zz"],
    "ASTROX 100ZZ", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["天斧88dpro", "天斧88d pro", "天斧88d", "88dpro", "88d pro", "ax88dpro", "ax88d"],
    "ASTROX 88D PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["天斧88spro", "天斧88s pro", "天斧88s", "88spro", "88s pro", "ax88spro", "ax88s"],
    "ASTROX 88S PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["天斧77pro", "天斧77 pro", "天斧77", "77pro", "ax77pro", "ax77"],
    "ASTROX 77 PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["天斧nextage", "天斧next age", "nextage", "axnextage"],
    "ASTROX NEXTAGE", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["疾光700", "nf700", "nanoflare700", "nanoflare 700"],
    "NANOFLARE 700", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["疾光800", "nf800", "nanoflare800", "nanoflare 800"],
    "NANOFLARE 800", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["疾光800pro", "nf800pro", "nanoflare800pro", "nanoflare 800 pro"],
    "NANOFLARE 800 PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["疾光1000z", "nf1000z", "nanoflare1000z", "nanoflare 1000z"],
    "NANOFLARE 1000Z", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["弓箭11pro", "弓箭11 pro", "弓箭11", "arc11pro", "arc11 pro", "arc11",
     "arcsaber11pro", "arcsaber 11 pro", "arcsaber11"],
    "ARCSABER 11 PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["弓箭7pro", "弓箭7 pro", "弓箭7", "arc7pro", "arc7 pro",
     "arcsaber7pro", "arcsaber 7 pro"],
    "ARCSABER 7 PRO", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["双刃10", "duora10", "duora 10"],
    "DUORA 10", "YONEX", "badminton_racket", "racket"
)
_register_model(
    ["vt-zf2", "vtzf2", "vt zf2", "voltric zf2", "zf2"],
    "VOLTRIC Z-FORCE II", "YONEX", "badminton_racket", "racket"
)

# === Victor Badminton Rackets ===
_register_model(
    ["龙牙之刃", "龙牙", "dragon fang", "thruster f"],
    "THRUSTER F 龙牙之刃", "Victor", "badminton_racket", "racket"
)
_register_model(
    ["龙牙2", "龙牙二代", "dragon fang 2", "thruster f 2"],
    "THRUSTER F 龙牙之刃 II", "Victor", "badminton_racket", "racket"
)
_register_model(
    ["神速100x", "神速100", "aursonic 100x", "ars100x"],
    "AURSONIC 100X", "Victor", "badminton_racket", "racket"
)
_register_model(
    ["驭10m", "驭10", "drivex 10m", "dx10m"],
    "DRIVEX 10M", "Victor", "badminton_racket", "racket"
)

# === Li-Ning Badminton Rackets ===
_register_model(
    ["雷霆80", "axforce80", "axforce 80"],
    "AXFORCE 80", "Li-Ning", "badminton_racket", "racket"
)
_register_model(
    ["雷霆90", "axforce90", "axforce 90", "雷霆90龙", "雷霆90虎"],
    "AXFORCE 90", "Li-Ning", "badminton_racket", "racket"
)
_register_model(
    ["战戟8000", "战戟8000", "bladex8000", "bladex 8000"],
    "BLADEX 8000", "Li-Ning", "badminton_racket", "racket"
)
_register_model(
    ["锋影800", "锋影800", "halberd800", "halberd 800"],
    "HALBERD 800", "Li-Ning", "badminton_racket", "racket"
)

# === Badminton Shuttlecocks ===
_register_model(
    ["as50", "as-50", "aerosensa50", "aerosensa 50"],
    "AEROSENSA 50", "YONEX", "badminton_shuttlecock", "shuttlecock"
)
_register_model(
    ["as40", "as-40", "aerosensa40"],
    "AEROSENSA 40", "YONEX", "badminton_shuttlecock", "shuttlecock"
)
_register_model(
    ["as30", "as-30", "aerosensa30"],
    "AEROSENSA 30", "YONEX", "badminton_shuttlecock", "shuttlecock"
)

# === Smartphone Models ===
_register_model(
    ["iphone16", "iphone 16", "ip16", "苹果16"],
    "iPhone 16", "Apple", "smartphone"
)
_register_model(
    ["iphone16pro", "iphone 16 pro", "ip16pro", "16pro"],
    "iPhone 16 Pro", "Apple", "smartphone"
)
_register_model(
    ["iphone16promax", "iphone 16 pro max", "ip16pm", "16pm", "16 pro max"],
    "iPhone 16 Pro Max", "Apple", "smartphone"
)
_register_model(
    ["iphone15", "iphone 15", "ip15", "苹果15"],
    "iPhone 15", "Apple", "smartphone"
)
_register_model(
    ["iphone15promax", "iphone 15 pro max", "ip15pm", "15pm"],
    "iPhone 15 Pro Max", "Apple", "smartphone"
)
_register_model(
    ["mate70", "mate 70", "m70", "华为mate70"],
    "Mate 70", "HUAWEI", "smartphone"
)
_register_model(
    ["mate70pro", "mate 70 pro", "m70pro"],
    "Mate 70 Pro", "HUAWEI", "smartphone"
)
_register_model(
    ["pura70", "pura 70", "p70", "华为pura70"],
    "Pura 70", "HUAWEI", "smartphone"
)
_register_model(
    ["mi15", "小米15", "xiaomi15", "xiaomi 15"],
    "Xiaomi 15", "Xiaomi", "smartphone"
)
_register_model(
    ["s25ultra", "s25 ultra", "s25u", "galaxys25"],
    "Galaxy S25 Ultra", "Samsung", "smartphone"
)

# === GPU Models ===
_register_model(
    ["rtx5090", "rtx 5090", "5090"],
    "RTX 5090", "NVIDIA", "graphics_card"
)
_register_model(
    ["rtx5080", "rtx 5080", "5080"],
    "RTX 5080", "NVIDIA", "graphics_card"
)
_register_model(
    ["rtx4090", "rtx 4090", "4090"],
    "RTX 4090", "NVIDIA", "graphics_card"
)
_register_model(
    ["rtx4080super", "rtx 4080 super", "4080s", "4080 super"],
    "RTX 4080 Super", "NVIDIA", "graphics_card"
)
_register_model(
    ["rtx4070ti", "rtx 4070 ti", "4070ti", "4070 ti"],
    "RTX 4070 Ti", "NVIDIA", "graphics_card"
)
_register_model(
    ["rx7900xtx", "rx 7900 xtx", "7900xtx"],
    "RX 7900 XTX", "AMD", "graphics_card"
)


# ═══════════════════════════════════════════════════════════════════════
# Category constraint: given a category, what's allowed/forbidden
# ═══════════════════════════════════════════════════════════════════════

# For each category, list sibling categories that are acceptable as fallback
CATEGORY_FALLBACK_ALLOWED: dict[str, set[str]] = {
    "badminton_racket": {"badminton_racket", "badminton_shuttlecock", "badminton_shoe", "tennis_racket"},
    "badminton_shuttlecock": {"badminton_racket", "badminton_shuttlecock", "badminton_shoe"},
    "smartphone": {"smartphone", "tablet"},
    "laptop": {"laptop", "tablet"},
    "graphics_card": {"graphics_card", "cpu", "monitor"},
    "headphone": {"headphone"},
    "shoe": {"shoe", "running_shoe", "badminton_shoe", "basketball"},
    "running_shoe": {"shoe", "running_shoe"},
    "gaming_console": {"gaming_console"},
    "tv": {"tv", "monitor"},
    "camera": {"camera"},
}


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=512)
def resolve_product(query: str) -> ProductEntity:
    """Resolve a user query to a structured ProductEntity.

    Tries in order:
      1. Exact model alias match → full entity
      2. Brand match + keyword → partial entity
      3. Category keyword match → category-only entity
      4. Fallback with empty entity
    """
    q = query.lower().strip()
    entity = ProductEntity()

    # ── 1. Try model alias match (most specific) ──
    # Sort by key length (longest first) for most specific match
    for alias in sorted(MODEL_DB, key=len, reverse=True):
        if alias in q:
            model = MODEL_DB[alias]
            entity.brand = model.brand
            entity.brand_aliases = _get_brand_aliases(model.brand)
            entity.product = model.canonical
            entity.product_aliases = model.aliases
            entity.category = model.category
            entity.subcategory = model.subcategory
            entity.confidence = 0.95
            entity.matched_alias = alias
            return entity

    # ── 2. Try brand-only match ──
    for brand_key in sorted(BRAND_DB, key=len, reverse=True):
        if brand_key in q:
            brand = BRAND_DB[brand_key]
            entity.brand = brand.canonical
            entity.brand_aliases = brand.aliases
            entity.confidence = 0.7

            # Infer category from brand's categories + query keywords
            for cat in brand.categories:
                cat_keywords = CATEGORY_HIERARCHY.get(cat, [])
                for kw in cat_keywords:
                    if kw.lower() in q:
                        entity.category = cat
                        entity.confidence = 0.8
                        break
                if entity.category:
                    break

            # If no specific category found, use brand's primary category
            if not entity.category and brand.categories:
                entity.category = brand.categories[0]
                entity.confidence = 0.6

            entity.matched_alias = brand_key
            return entity

    # ── 3. Try category-only match ──
    for kw in sorted(_KEYWORD_TO_CATEGORY, key=len, reverse=True):
        if kw in q:
            entity.category = _KEYWORD_TO_CATEGORY[kw]
            entity.confidence = 0.5
            entity.matched_alias = kw
            return entity

    # ── 4. Nothing detected ──
    entity.category = "general"
    entity.confidence = 0.0
    return entity


def _get_brand_aliases(canonical_brand: str) -> list[str]:
    """Get all known aliases for a brand."""
    info = BRAND_DB.get(canonical_brand.lower())
    if info:
        return info.aliases
    return []


def get_category_constraint(entity: ProductEntity) -> set[str]:
    """Get the set of allowed categories given a detected entity.

    Returns a set of category names that are acceptable for this query.
    If entity has a category, only that category and its fallback siblings are allowed.
    If no category detected, returns empty set (no constraint).
    """
    if not entity.category or entity.category == "general":
        return set()  # No constraint — allow all categories

    cat = entity.category
    allowed = CATEGORY_FALLBACK_ALLOWED.get(cat, {cat})
    return allowed


def get_brand_constraint(entity: ProductEntity) -> set[str]:
    """Get the set of allowed brand names given a detected entity."""
    if not entity.brand:
        return set()  # No constraint — allow all brands
    return {entity.brand.lower()} | {a.lower() for a in entity.brand_aliases}


def get_model_constraint(entity: ProductEntity) -> str:
    """Get the canonical model name that must be matched."""
    return entity.product


def validate_result(entity: ProductEntity, result: dict) -> tuple[bool, str]:
    """Validate a search result against detected entity constraints.

    Returns (is_valid, reason).
    """
    if not entity.is_valid or entity.confidence < 0.5:
        return True, "no entity constraint"

    result_brand = (result.get("brand") or "").lower()
    result_category = (result.get("category") or "").lower()
    result_name = (result.get("name") or result.get("title", "")).lower()

    # 1. Brand check
    if entity.brand:
        allowed_brands = get_brand_constraint(entity)
        if allowed_brands and result_brand:
            if result_brand not in allowed_brands:
                # Also check if result name contains the brand
                name_has_brand = any(b in result_name for b in allowed_brands)
                if not name_has_brand:
                    return False, f"brand mismatch: expected {entity.brand}, got {result_brand}"

    # 2. Category check (most important)
    if entity.category and entity.category != "general":
        allowed_cats = get_category_constraint(entity)
        if allowed_cats and result_category:
            if result_category not in allowed_cats:
                return False, f"category mismatch: expected {entity.category}, got {result_category}"

    # 3. Model check (loose — only for high-confidence entity matches)
    if entity.product and entity.confidence >= 0.8:
        model_parts = entity.product.lower().replace("-", " ").replace("_", " ").split()
        name_parts = result_name.split()
        overlap = sum(1 for mp in model_parts if any(mp in np for np in name_parts))
        if len(model_parts) > 1 and overlap == 0:
            return False, f"model mismatch: expected {entity.product}"

    return True, "ok"


def get_all_brands_for_category(category: str) -> list[str]:
    """Get all brand canonical names for a given category."""
    brands = []
    for info in BRAND_DB.values():
        if category in info.categories:
            if info.canonical not in brands:
                brands.append(info.canonical)
    return brands


def get_all_models_for_category(category: str) -> list[str]:
    """Get all model names for a given category."""
    models = []
    for model in MODEL_DB.values():
        if model.category == category:
            if model.canonical not in models:
                models.append(model.canonical)
    return models
