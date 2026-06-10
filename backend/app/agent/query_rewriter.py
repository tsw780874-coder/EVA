"""Query Rewriter — expand queries for maximum recall across all search layers.

Provides:
  1. Synonym expansion (Chinese ↔ English, brand aliases)
  2. Model abbreviation resolution
  3. Progressive query degradation for fallback search
  4. Normalized product name extraction

Usage:
    from app.agent.query_rewriter import rewrite_query, degrade_query

    expansions = rewrite_query("iPhone16 Pro Max 1TB 白色")
    # → ["Apple iPhone 16 Pro Max 1TB 白色", "苹果16 Pro Max", ...]

    degraded = degrade_query("RTX5090冰龙OC版")
    # → ["RTX5090冰龙", "RTX5090", "RTX50系列显卡", "NVIDIA显卡"]
"""

import re
from functools import lru_cache
from typing import NamedTuple


# ═══════════════════════════════════════════════════════════════════════
# Brand knowledge base — Chinese ↔ English aliases
# ═══════════════════════════════════════════════════════════════════════

BRAND_ALIASES: dict[str, list[str]] = {
    "苹果": ["Apple", "iPhone", "iPad", "MacBook", "AirPods", "Apple Watch"],
    "apple": ["苹果", "iPhone", "iPad", "MacBook"],
    "华为": ["HUAWEI", "Huawei", "Mate", "Pura", "鸿蒙"],
    "huawei": ["华为", "HUAWEI", "Mate"],
    "小米": ["Xiaomi", "Redmi", "红米", "POCO"],
    "xiaomi": ["小米", "Redmi"],
    "三星": ["Samsung", "Galaxy", "S系列"],
    "samsung": ["三星", "Galaxy"],
    "oppo": ["OPPO", "Find", "Reno"],
    "vivo": ["vivo", "X系列", "iQOO"],
    "荣耀": ["Honor", "Magic"],
    "honor": ["荣耀"],
    "一加": ["OnePlus", "一加"],
    "oneplus": ["一加", "OnePlus"],
    "索尼": ["Sony", "SONY", "Xperia"],
    "sony": ["索尼", "SONY"],
    "谷歌": ["Google", "Pixel"],
    "google": ["谷歌", "Pixel"],
    "微软": ["Microsoft", "Surface"],
    "microsoft": ["微软", "Surface"],
    "联想": ["Lenovo", "ThinkPad", "拯救者", "Yoga", "小新"],
    "lenovo": ["联想", "ThinkPad", "Legion"],
    "戴尔": ["Dell", "XPS", "Alienware"],
    "dell": ["戴尔", "Dell"],
    "惠普": ["HP", "惠普", "Spectre", "暗影精灵"],
    "hp": ["惠普", "HP"],
    "华硕": ["ASUS", "ROG", "华硕"],
    "asus": ["华硕", "ASUS", "ROG"],
    "宏碁": ["Acer", "宏碁"],
    "acer": ["宏碁", "Acer"],
    "任天堂": ["Nintendo", "Switch"],
    "nintendo": ["任天堂", "Switch"],
    "索尼游戏": ["PlayStation", "PS5"],
    "playstation": ["PS5", "索尼"],
    "微软游戏": ["Xbox", "Xbox Series"],
    "xbox": ["微软", "Xbox"],
    "英伟达": ["NVIDIA", "GeForce", "RTX"],
    "nvidia": ["英伟达", "NVIDIA", "GeForce"],
    "amd": ["AMD", "Radeon", "Ryzen", "锐龙"],
    "英特尔": ["Intel", "Core", "酷睿"],
    "intel": ["英特尔", "Intel", "Core"],
    "大疆": ["DJI", "大疆"],
    "dji": ["大疆", "DJI"],
    "戴森": ["Dyson", "戴森"],
    "dyson": ["戴森", "Dyson"],
    "格力": ["Gree", "格力"],
    "美的": ["Midea", "美的"],
    "海尔": ["Haier", "海尔"],
    "石头": ["Roborock", "石头"],
    "科沃斯": ["Ecovacs", "科沃斯"],
    "追觅": ["Dreame", "追觅"],
    "耐克": ["Nike", "AJ", "Air Jordan", "Dunk"],
    "nike": ["耐克", "Nike"],
    "阿迪达斯": ["Adidas", "adidas", "阿迪"],
    "adidas": ["阿迪达斯", "阿迪", "Adidas"],
    "安踏": ["ANTA", "安踏"],
    "李宁": ["Li-Ning", "李宁"],
    "特斯拉": ["Tesla", "特斯拉"],
    "比亚迪": ["BYD", "比亚迪"],
    "奔驰": ["Mercedes-Benz", "Benz", "奔驰"],
    "宝马": ["BMW", "宝马"],
    "奥迪": ["Audi", "奥迪"],
}


def _resolve_brand(query: str) -> list[str]:
    """Find matching brands in query and return all aliases."""
    q = query.lower()
    aliases: set[str] = set()
    for brand, names in BRAND_ALIASES.items():
        if brand.lower() in q:
            aliases.update(names)
            aliases.add(brand)
    return list(aliases)


# ═══════════════════════════════════════════════════════════════════════
# Model abbreviation resolution
# ═══════════════════════════════════════════════════════════════════════

MODEL_EXPANSIONS: dict[str, str] = {
    # Phone models
    "iphone16": "iPhone 16",
    "iphone15": "iPhone 15",
    "iphone14": "iPhone 14",
    "ip16": "iPhone 16",
    "ip15": "iPhone 15",
    "16pm": "iPhone 16 Pro Max",
    "16p": "iPhone 16 Pro",
    "15pm": "iPhone 15 Pro Max",
    "15p": "iPhone 15 Pro",
    "m70": "Mate 70",
    "m60": "Mate 60",
    "p70": "Pura 70",
    "p60": "Pura 60",
    "mi15": "Xiaomi 15",
    "mi14": "Xiaomi 14",
    "s25u": "Galaxy S25 Ultra",
    "s24u": "Galaxy S24 Ultra",
    # GPUs
    "rtx5090": "RTX 5090",
    "rtx5080": "RTX 5080",
    "rtx4090": "RTX 4090",
    "rtx4080": "RTX 4080",
    "rtx4070": "RTX 4070",
    "rtx4060": "RTX 4060",
    "rx7900": "RX 7900 XTX",
    "rx7800": "RX 7800 XT",
    # CPUs
    "i9-14900k": "Intel Core i9-14900K",
    "i7-14700k": "Intel Core i7-14700K",
    "i5-14600k": "Intel Core i5-14600K",
    "r9-7950x": "AMD Ryzen 9 7950X",
    "r7-7800x3d": "AMD Ryzen 7 7800X3D",
    # Laptops
    "mbp14": "MacBook Pro 14",
    "mbp16": "MacBook Pro 16",
    "mba15": "MacBook Air 15",
    "mba13": "MacBook Air 13",
    # Consoles
    "ps5pro": "PlayStation 5 Pro",
    "switch2": "Nintendo Switch 2",
    # Tablets
    "ipp11": "iPad Pro 11",
    "ipp13": "iPad Pro 13",
    "ipa11": "iPad Air 11",
    "ipa13": "iPad Air 13",
}


def _resolve_model_abbrev(query: str) -> str:
    """Expand known model abbreviations in the query."""
    q = query.lower()
    # Sort by length (longest first) to match most specific first
    for abbrev in sorted(MODEL_EXPANSIONS, key=len, reverse=True):
        pattern = re.sub(r"[\s-]", r"[\\s-]*", re.escape(abbrev))
        if re.search(pattern, q, re.IGNORECASE):
            expanded = MODEL_EXPANSIONS[abbrev]
            return re.sub(pattern, expanded, query, count=1, flags=re.IGNORECASE)
    return query


# ═══════════════════════════════════════════════════════════════════════
# Attribute keywords for degradation
# ═══════════════════════════════════════════════════════════════════════

_ATTRIBUTE_PATTERNS = [
    # Storage / memory
    r'\d+\s*(TB|GB|MB|太字节|千兆)',
    # Color
    r'(白|黑|红|蓝|绿|紫|金|银|灰|粉|黄|橙|深空|午夜|星光|远峰|苍岭|原色|钛[金属色]*)\s*(色|款|版)?',
    # Year / generation
    r'(20\d{2})\s*(款|版|年款|年版)?',
    # Condition
    r'(全新|二手|翻新|官翻|国行|港版|美版|日版|欧版|韩版)',
    # Edition keywords
    r'(冰龙|超龙|猛禽|火神|魔龙|雪豹|天启|金属大师|星耀|电竞之心|万图师)',
    r'(Ultra|Pro|Max|Plus|Mini|Lite|SE|标准版|高配版|旗舰版|青春版)',
    r'(OC|超频|水冷|风冷|液冷)',
]


def _strip_attributes(query: str, level: int = 1) -> str:
    """Strip attribute modifiers from query for degraded search.

    Level 1: Remove color, storage, condition modifiers
    Level 2: Remove edition/trim modifiers
    Level 3: Keep only brand + core product category
    """
    result = query.strip()

    if level >= 1:
        for pattern in _ATTRIBUTE_PATTERNS[:6]:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    if level >= 2:
        for pattern in _ATTRIBUTE_PATTERNS[6:]:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

    # Clean up whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    if level >= 3:
        # Keep only the first 2-4 characters (likely the brand/model core)
        words = result.split()
        if len(words) > 3:
            result = ' '.join(words[:3])

    return result or query


# ═══════════════════════════════════════════════════════════════════════
# Category hierarchy for ultimate fallback
# ═══════════════════════════════════════════════════════════════════════

CATEGORY_MAP: dict[str, str] = {
    # Phone → category
    "手机": "智能手机",
    "iPhone": "智能手机",
    "iphone": "智能手机",
    "华为": "智能手机",
    "小米": "智能手机",
    "三星": "智能手机",
    # GPU → category
    "显卡": "独立显卡",
    "RTX": "NVIDIA显卡",
    "rtx": "NVIDIA显卡",
    "RX": "AMD显卡",
    "rx": "AMD显卡",
    # Laptop → category
    "笔记本": "笔记本电脑",
    "游戏本": "游戏笔记本电脑",
    "MacBook": "笔记本电脑",
    "ThinkPad": "商务笔记本电脑",
    # Headphones → category
    "耳机": "耳机",
    "AirPods": "真无线耳机",
    # Shoes → category
    "鞋": "运动鞋",
    "AJ": "篮球鞋",
    "Dunk": "休闲鞋",
    # Watch → category
    "手表": "手表",
    "Apple Watch": "智能手表",
    # Tablet → category
    "平板": "平板电脑",
    "iPad": "平板电脑",
    # Console → category
    "PS5": "游戏主机",
    "Switch": "游戏主机",
    "Xbox": "游戏主机",
    # Appliance → category
    "空调": "空调",
    "电视": "电视机",
    "扫地": "扫地机器人",
    "冰箱": "冰箱",
    "洗衣机": "洗衣机",
}


def _resolve_category(query: str) -> str:
    """Map query to a broad product category for ultimate fallback."""
    q = query.lower()
    for keyword, category in sorted(CATEGORY_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if keyword.lower() in q:
            return category
    return "热门商品"


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════


class ExpandedQuery(NamedTuple):
    """Result of query rewriting."""
    original: str           # Original query
    expanded: list[str]     # All expanded query variants (including original)
    brands: list[str]       # Detected brand names
    core_product: str       # Core product name (brand + model, no attributes)
    category: str           # Broad product category


@lru_cache(maxsize=256)
def rewrite_query(query: str) -> ExpandedQuery:
    """Expand a user query into multiple search variants.

    Returns an ExpandedQuery with:
      - original: the original query text
      - expanded: list of query variants to try (sorted by specificity)
      - brands: detected brand names/aliases
      - core_product: query with attributes stripped (brand + model only)
      - category: broad product category for ultimate fallback
    """
    variants: list[str] = [query]

    # 1. Model abbreviation expansion
    expanded_model = _resolve_model_abbrev(query)
    if expanded_model != query:
        variants.append(expanded_model)

    # 2. Brand aliases
    brands = _resolve_brand(query)
    for brand in brands[:3]:  # Limit to top 3 brand aliases
        if brand.lower() not in query.lower():
            variant = f"{brand} {query}"
            if variant not in variants:
                variants.append(variant)

    # 3. Strip to core product (Level 1 degradation)
    core_product = _strip_attributes(query, level=1)
    if core_product != query and core_product not in variants:
        variants.append(core_product)

    # 4. Broader core (Level 2)
    core_broad = _strip_attributes(query, level=2)
    if core_broad != core_product and core_broad not in variants:
        variants.append(core_broad)

    # 5. Category
    category = _resolve_category(query)

    # 6. Clean duplicates while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        v_lower = v.lower().strip()
        if v_lower and v_lower not in seen:
            seen.add(v_lower)
            unique.append(v)

    return ExpandedQuery(
        original=query,
        expanded=unique,
        brands=brands,
        core_product=core_product,
        category=category,
    )


@lru_cache(maxsize=256)
def degrade_query(query: str) -> list[tuple[str, int]]:
    """Progressive query degradation for fallback search.

    Returns list of (query_variant, degradation_level) tuples.
    Level 0: exact query
    Level 1: remove attributes (color, storage, condition)
    Level 2: remove edition/trim modifiers
    Level 3: brand + model only (no modifiers)
    Level 4: brand + category
    Level 5: category only
    """
    expanded = rewrite_query(query)
    result: list[tuple[str, int]] = []

    seen: set[str] = set()

    def _add(q: str, level: int) -> None:
        key = q.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append((q, level))

    # Level 0: All expanded variants
    for v in expanded.expanded:
        _add(v, 0)

    # Level 1-2: Attribute stripping
    for level in [1, 2]:
        stripped = _strip_attributes(query, level)
        _add(stripped, level)

    # Level 3: Core product only
    core = _strip_attributes(query, 3)
    _add(core, 3)

    # Level 4: Brand + category
    if expanded.brands:
        cat = expanded.category
        for brand in expanded.brands[:2]:
            _add(f"{brand} {cat}", 4)
    _add(f"{core.split()[0] if core.split() else core} {expanded.category}", 4)

    # Level 5: Category only
    _add(expanded.category, 5)

    return result


def extract_search_keywords(query: str) -> list[str]:
    """Extract key search terms from query for keyword matching."""
    # Remove common stop words
    stop_words = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
                  "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
                  "你", "会", "着", "没有", "看", "好", "自己", "这", "买",
                  "哪个", "哪里", "什么", "怎么", "多少", "推荐", "最好", "最便宜",
                  "性价比", "值得", "划算", "帮我"}
    words = re.findall(r'[一-鿿]+|[a-zA-Z0-9]+', query)
    return [w for w in words if w.lower() not in stop_words and len(w) > 1]
