"""Confidence Tier System + Fast Search Mode.

Confidence Tiers:
  A-tier (Official)  — Brand official website, official flagship store → 95-100%
  B-tier (Flagship)  — Official JD/Tmall flagship stores → 80-94%
  C-tier (Third-party)— Third-party sellers, general e-commerce → 50-79%
  D-tier (UGC)       — Forums, blogs, user content → 10-49%
  E-tier (Unknown)   — Unverified sources → 0-9%

Fast Search Mode:
  When enabled, skips: image fetching, review scraping, detail page parsing
  Returns only: title, platform, link, price
  Target: <1s first byte, <3s complete result

Usage:
    from app.agent.confidence_tiers import rate_source, TierLevel, FastSearchConfig
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TierLevel(str, Enum):
    A_OFFICIAL = "A"      # Brand official website/store
    B_FLAGSHIP = "B"      # Official e-commerce flagship store
    C_THIRD_PARTY = "C"   # Third-party platform sellers
    D_UGC = "D"           # Forums, blogs, user content
    E_UNKNOWN = "E"       # Completely unverified


# ═══════════════════════════════════════════════════════════════════════
# Source tier mapping
# ═══════════════════════════════════════════════════════════════════════

# Each source domain gets a tier rating
_SOURCE_TIERS: dict[str, tuple[TierLevel, str]] = {
    # A-tier: Official
    "apple.com": (TierLevel.A_OFFICIAL, "Apple 官方网站"),
    "apple.cn": (TierLevel.A_OFFICIAL, "Apple 中国大陆"),
    "yonex.com": (TierLevel.A_OFFICIAL, "YONEX 官方网站"),
    "yonex.cn": (TierLevel.A_OFFICIAL, "YONEX 中国"),
    "nvidia.com": (TierLevel.A_OFFICIAL, "NVIDIA 官方网站"),
    "samsung.com": (TierLevel.A_OFFICIAL, "Samsung 官方网站"),
    "huawei.com": (TierLevel.A_OFFICIAL, "华为 官方网站"),
    "xiaomi.com": (TierLevel.A_OFFICIAL, "小米 官方网站"),
    "sony.com": (TierLevel.A_OFFICIAL, "Sony 官方网站"),
    "intel.com": (TierLevel.A_OFFICIAL, "Intel 官方网站"),
    "amd.com": (TierLevel.A_OFFICIAL, "AMD 官方网站"),
    "nike.com": (TierLevel.A_OFFICIAL, "Nike 官方网站"),
    "adidas.com": (TierLevel.A_OFFICIAL, "Adidas 官方网站"),
    "dyson.com": (TierLevel.A_OFFICIAL, "Dyson 官方网站"),

    # B-tier: Official e-commerce flagships
    "mall.jd.com": (TierLevel.B_FLAGSHIP, "京东官方旗舰店"),
    "tmall.com": (TierLevel.B_FLAGSHIP, "天猫官方旗舰店"),
    "jd.com": (TierLevel.B_FLAGSHIP, "京东自营"),
    "amazon.cn": (TierLevel.B_FLAGSHIP, "亚马逊自营"),
    "sunin.com": (TierLevel.B_FLAGSHIP, "苏宁自营"),

    # C-tier: Third-party platforms
    "taobao.com": (TierLevel.C_THIRD_PARTY, "淘宝"),
    "pinduoduo.com": (TierLevel.C_THIRD_PARTY, "拼多多"),
    "dewu.com": (TierLevel.C_THIRD_PARTY, "得物"),
    "vip.com": (TierLevel.C_THIRD_PARTY, "唯品会"),
    "shihuo.cn": (TierLevel.C_THIRD_PARTY, "识货"),
    "xianyu.com": (TierLevel.C_THIRD_PARTY, "闲鱼"),

    # D-tier
    "zhihu.com": (TierLevel.D_UGC, "知乎"),
    "smzdm.com": (TierLevel.D_UGC, "什么值得买"),
    "xiaohongshu.com": (TierLevel.D_UGC, "小红书"),
    "bilibili.com": (TierLevel.D_UGC, "B站"),
    "tieba.baidu.com": (TierLevel.D_UGC, "贴吧"),
}

# Source type mapping (internal source labels → TierLevel)
_SOURCE_TYPE_TIERS: dict[str, TierLevel] = {
    "hot_products": TierLevel.B_FLAGSHIP,   # Curated hot products = high trust
    "product_cache": TierLevel.B_FLAGSHIP,  # Cached verified products
    "rag": TierLevel.B_FLAGSHIP,            # RAG from knowledge base
    "database": TierLevel.A_OFFICIAL,       # Internal database records
    "official": TierLevel.A_OFFICIAL,
    "live_search": TierLevel.C_THIRD_PARTY, # Real-time search
    "similar_search": TierLevel.C_THIRD_PARTY,
    "link_fallback": TierLevel.D_UGC,        # Generated links
    "ecommerce_web": TierLevel.C_THIRD_PARTY,  # Search engine → real e-commerce links
    "simulated": TierLevel.E_UNKNOWN,        # Template/simulated data
    "llm_web_search": TierLevel.D_UGC,
}


# ═══════════════════════════════════════════════════════════════════════
# Tier configuration
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TierConfig:
    level: TierLevel
    label: str
    min_confidence: float
    max_confidence: float
    color: str          # Emoji indicator
    description: str
    trust_actions: list[str]  # What actions are safe with this tier


TIER_CONFIGS: dict[TierLevel, TierConfig] = {
    TierLevel.A_OFFICIAL: TierConfig(
        TierLevel.A_OFFICIAL, "品牌官方", 95.0, 100.0, "🟢",
        "官方品牌渠道，信息100%可信", ["直接引用", "价格可信", "参数可信"]
    ),
    TierLevel.B_FLAGSHIP: TierConfig(
        TierLevel.B_FLAGSHIP, "官方旗舰店", 80.0, 94.0, "🟢",
        "电商官方旗舰店/自营，信息高度可信", ["直接引用", "价格可信"]
    ),
    TierLevel.C_THIRD_PARTY: TierConfig(
        TierLevel.C_THIRD_PARTY, "第三方平台", 50.0, 79.0, "🟡",
        "第三方平台商家，信息基本可信", ["参考使用", "价格仅供参考"]
    ),
    TierLevel.D_UGC: TierConfig(
        TierLevel.D_UGC, "用户内容", 10.0, 49.0, "🟠",
        "论坛/博客/用户内容，信息需验证", ["仅作参考", "不建议直接引用"]
    ),
    TierLevel.E_UNKNOWN: TierConfig(
        TierLevel.E_UNKNOWN, "未知来源", 0.0, 9.0, "🔴",
        "无法验证来源，信息不可信", ["不可引用", "需要进一步验证"]
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# Source rating API
# ═══════════════════════════════════════════════════════════════════════

def rate_url(url: str) -> tuple[TierLevel, str]:
    """Rate a product URL by its domain tier."""
    if not url:
        return TierLevel.E_UNKNOWN, "无链接"
    url_l = url.lower()
    for domain, (tier, label) in _SOURCE_TIERS.items():
        if domain in url_l:
            return tier, label
    return TierLevel.C_THIRD_PARTY, "电商平台"


def rate_source(source_type: str) -> tuple[TierLevel, str]:
    """Rate a product by its source type label."""
    tier = _SOURCE_TYPE_TIERS.get(source_type)
    if tier:
        config = TIER_CONFIGS[tier]
        return tier, config.label
    return TierLevel.E_UNKNOWN, "未知来源"


def get_tier_display(source_type: str, confidence: float = 0) -> str:
    """Get a human-readable tier display string."""
    tier, label = rate_source(source_type)
    config = TIER_CONFIGS[tier]
    return f"{config.color} {label} (可信度: {confidence:.0f}%)"


def get_min_returnable_tier() -> TierLevel:
    """Get the minimum tier that can still be returned to users."""
    return TierLevel.D_UGC  # C-tier and above are returnable


# ═══════════════════════════════════════════════════════════════════════
# Fast Search Mode
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class FastSearchConfig:
    """Configuration for fast/slim search mode."""
    enabled: bool = False
    skip_images: bool = True           # Don't fetch/generate images
    skip_reviews: bool = True          # Don't scrape reviews
    skip_details: bool = True          # Don't parse detail pages
    skip_llm_summary: bool = False     # Skip LLM summarization
    max_products: int = 3              # Return fewer products
    live_search_timeout: float = 3.0   # Shorter timeout for live search
    target_first_byte_ms: int = 800    # Target <1s
    target_complete_ms: int = 3000     # Target <3s

    def to_dict(self) -> dict:
        return {
            "mode": "fast",
            "skip_images": self.skip_images,
            "skip_reviews": self.skip_reviews,
            "target_ms": self.target_complete_ms,
        }


def create_fast_config() -> FastSearchConfig:
    """Create a fast search configuration."""
    return FastSearchConfig(enabled=True)


def create_full_config() -> FastSearchConfig:
    """Create a full/complete search configuration."""
    return FastSearchConfig(
        enabled=False, skip_images=False, skip_reviews=False, skip_details=False,
        max_products=5, live_search_timeout=6.0,
        target_first_byte_ms=2000, target_complete_ms=10000,
    )


def strip_to_essentials(product: dict) -> dict:
    """Strip a product dict to essential fields only (fast mode)."""
    return {
        "title": product.get("title") or product.get("name", ""),
        "price": product.get("price", ""),
        "platform": product.get("platform", ""),
        "url": product.get("url", ""),
        "confidence": product.get("confidence", 0),
        "source": product.get("source", ""),
        "tier": rate_source(product.get("source", ""))[0].value,
    }


# ═══════════════════════════════════════════════════════════════════════
# Quality gate — minimum bar for returning results
# ═══════════════════════════════════════════════════════════════════════

QUALITY_GATE = {
    "min_confidence_to_return": 5.0,     # Absolute minimum confidence
    "min_tier_to_return": TierLevel.E_UNKNOWN,  # Any tier can be returned
    "require_url": True,                  # Must have a URL (even if search link)
    "require_price": False,               # Price is nice but not required
    "require_image": False,               # Image is NOT required
    "require_rating": False,              # Rating is NOT required
    "require_reviews": False,             # Reviews are NOT required
    "min_products_to_return": 1,          # Return even 1 product
    "max_search_layers": 6,               # Before giving up
}


def passes_quality_gate(product: dict) -> tuple[bool, str]:
    """Check if a product meets the minimum quality requirements to be shown."""
    if QUALITY_GATE["require_url"] and not product.get("url"):
        return False, "缺少商品链接"

    conf = product.get("confidence", 0) or 0
    if conf < QUALITY_GATE["min_confidence_to_return"]:
        return False, f"可信度过低({conf:.0f}%)"

    return True, "ok"


def filter_by_quality_gate(products: list[dict]) -> list[dict]:
    """Filter products that pass the quality gate."""
    passed = []
    for p in products:
        ok, reason = passes_quality_gate(p)
        if ok:
            passed.append(p)
    return passed
