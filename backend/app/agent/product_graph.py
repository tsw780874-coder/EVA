"""Product Knowledge Graph — Brand→Series→Model→Spec hierarchical relationships.

Models products as a graph:
  Brand → Series → Model → (specs, user_level, price_range, competitors)

Enables:
  - "Same series" recommendations (ASTROX 99 PRO → ASTROX 100ZZ)
  - "Same brand" alternatives (YONEX → Victor, Li-Ning)
  - "Same category + user level" matching
  - Competitor product suggestions
  - Up-sell / cross-sell (99 PRO → 100ZZ as upgrade)

Usage:
    from app.agent.product_graph import (
        get_same_series, get_competitors, get_upgrade_path, traverse_graph
    )
"""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# Graph node types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ProductNode:
    """A node in the product knowledge graph."""
    id: str                          # Unique identifier
    name: str                        # Product/model name
    brand: str                       # Brand canonical name
    series: str                      # Product series (e.g., "ASTROX", "iPhone", "RTX 50")
    category: str                    # Product category
    model: str                       # Specific model
    tier: str = "mid"                # "entry" | "mid" | "high" | "flagship"
    user_level: str = "intermediate" # "beginner" | "intermediate" | "advanced" | "pro"
    price_min: float = 0.0
    price_max: float = 0.0
    generation: str = ""             # "2024" | "2025" | etc.
    key_specs: list[str] = field(default_factory=list)  # ["4U", "进攻型", "硬中杆"]
    competitors: list[str] = field(default_factory=list)  # Node IDs of direct competitors
    parent_series: str = ""          # Parent series node ID
    successor: str = ""              # Next-gen successor node ID
    predecessor: str = ""            # Previous-gen node ID


# ═══════════════════════════════════════════════════════════════════════
# Product Graph Database
# ═══════════════════════════════════════════════════════════════════════

_PRODUCT_GRAPH: dict[str, ProductNode] = {}


def _reg(
    nid: str, name: str, brand: str, series: str, category: str, model: str,
    tier: str = "mid", user_level: str = "intermediate",
    price_min: float = 0, price_max: float = 0,
    generation: str = "", key_specs: list[str] | None = None,
    competitors: list[str] | None = None,
    parent_series: str = "", successor: str = "", predecessor: str = "",
):
    _PRODUCT_GRAPH[nid] = ProductNode(
        id=nid, name=name, brand=brand, series=series, category=category,
        model=model, tier=tier, user_level=user_level,
        price_min=price_min, price_max=price_max, generation=generation,
        key_specs=key_specs or [], competitors=competitors or [],
        parent_series=parent_series, successor=successor, predecessor=predecessor,
    )


# ═══ YONEX Badminton Rackets ═══
_reg("astrox-series", "ASTROX 系列", "YONEX", "ASTROX", "badminton_racket", "",
     tier="high", user_level="advanced", generation="2024")
_reg("ax99pro", "ASTROX 99 PRO", "YONEX", "ASTROX", "badminton_racket", "ASTROX 99 PRO",
     tier="flagship", user_level="pro", price_min=1680, price_max=1980,
     key_specs=["进攻型", "硬中杆", "头重", "4U/3U"],
     competitors=["thruster-f", "axforce80"],
     parent_series="astrox-series", predecessor="ax99")
_reg("ax100zz", "ASTROX 100ZZ", "YONEX", "ASTROX", "badminton_racket", "ASTROX 100ZZ",
     tier="flagship", user_level="pro", price_min=1780, price_max=2080,
     key_specs=["进攻型", "超细中杆", "头重", "4U/3U"],
     competitors=["thruster-f-2", "axforce90"],
     parent_series="astrox-series", successor="ax99pro")
_reg("ax88dpro", "ASTROX 88D PRO", "YONEX", "ASTROX", "badminton_racket", "ASTROX 88D PRO",
     tier="high", user_level="advanced", price_min=1580, price_max=1780,
     key_specs=["进攻型", "硬中杆", "后场", "4U"],
     competitors=["aursonic100x", "halberd800"],
     parent_series="astrox-series")
_reg("ax88spro", "ASTROX 88S PRO", "YONEX", "ASTROX", "badminton_racket", "ASTROX 88S PRO",
     tier="high", user_level="advanced", price_min=1580, price_max=1780,
     key_specs=["控制型", "适中中杆", "前场", "4U"],
     competitors=[],
     parent_series="astrox-series")
_reg("ax77pro", "ASTROX 77 PRO", "YONEX", "ASTROX", "badminton_racket", "ASTROX 77 PRO",
     tier="high", user_level="intermediate", price_min=1380, price_max=1580,
     key_specs=["进攻型", "适中中杆", "全能", "4U"],
     competitors=[],
     parent_series="astrox-series")
_reg("axnextage", "ASTROX NEXTAGE", "YONEX", "ASTROX", "badminton_racket", "ASTROX NEXTAGE",
     tier="mid", user_level="intermediate", price_min=1080, price_max=1280,
     key_specs=["进攻型", "适中中杆", "入门进攻", "4U/5U"],
     competitors=[],
     parent_series="astrox-series")

_reg("nanoflare-series", "NANOFLARE 系列", "YONEX", "NANOFLARE", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("nf1000z", "NANOFLARE 1000Z", "YONEX", "NANOFLARE", "badminton_racket", "NANOFLARE 1000Z",
     tier="flagship", user_level="pro", price_min=1680, price_max=1880,
     key_specs=["速度型", "超细中杆", "头轻", "4U/5U"],
     competitors=["aursonic100x"],
     parent_series="nanoflare-series")
_reg("nf800pro", "NANOFLARE 800 PRO", "YONEX", "NANOFLARE", "badminton_racket", "NANOFLARE 800 PRO",
     tier="high", user_level="advanced", price_min=1480, price_max=1680,
     key_specs=["速度型", "硬中杆", "头轻", "4U/5U"],
     competitors=[],
     parent_series="nanoflare-series")
_reg("nf700", "NANOFLARE 700", "YONEX", "NANOFLARE", "badminton_racket", "NANOFLARE 700",
     tier="mid", user_level="intermediate", price_min=1280, price_max=1480,
     key_specs=["速度型", "适中中杆", "头轻", "4U/5U"],
     competitors=[],
     parent_series="nanoflare-series")

_reg("arcsaber-series", "ARCSABER 系列", "YONEX", "ARCSABER", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("arc11pro", "ARCSABER 11 PRO", "YONEX", "ARCSABER", "badminton_racket", "ARCSABER 11 PRO",
     tier="flagship", user_level="pro", price_min=1580, price_max=1780,
     key_specs=["控制型", "适中中杆", "均衡", "4U/3U"],
     competitors=["bladex8000"],
     parent_series="arcsaber-series")
_reg("arc7pro", "ARCSABER 7 PRO", "YONEX", "ARCSABER", "badminton_racket", "ARCSABER 7 PRO",
     tier="mid", user_level="beginner", price_min=1280, price_max=1480,
     key_specs=["控制型", "软中杆", "均衡", "4U/5U"],
     competitors=[],
     parent_series="arcsaber-series")

# ═══ Victor Badminton ═══
_reg("thruster-series", "THRUSTER 系列", "Victor", "THRUSTER", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("thruster-f", "THRUSTER F 龙牙之刃", "Victor", "THRUSTER", "badminton_racket", "THRUSTER F",
     tier="flagship", user_level="pro", price_min=1480, price_max=1680,
     key_specs=["进攻型", "硬中杆", "头重", "4U/3U"],
     competitors=["ax99pro", "axforce80"],
     parent_series="thruster-series")
_reg("thruster-f-2", "THRUSTER F 龙牙之刃 II", "Victor", "THRUSTER", "badminton_racket", "THRUSTER F II",
     tier="flagship", user_level="pro", price_min=1580, price_max=1780,
     key_specs=["进攻型", "超硬中杆", "头重", "4U/3U"],
     competitors=["ax100zz"],
     parent_series="thruster-series", successor="thruster-f")

_reg("aursonic-series", "AURSONIC 系列", "Victor", "AURSONIC", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("aursonic100x", "AURSONIC 100X", "Victor", "AURSONIC", "badminton_racket", "AURSONIC 100X",
     tier="flagship", user_level="pro", price_min=1380, price_max=1580,
     key_specs=["速度型", "适中中杆", "全面", "4U"],
     competitors=["nf1000z"],
     parent_series="aursonic-series")

# ═══ Li-Ning Badminton ═══
_reg("axforce-series", "AXFORCE 系列", "Li-Ning", "AXFORCE", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("axforce80", "AXFORCE 80", "Li-Ning", "AXFORCE", "badminton_racket", "AXFORCE 80",
     tier="flagship", user_level="pro", price_min=1280, price_max=1480,
     key_specs=["进攻型", "硬中杆", "头重", "4U/3U"],
     competitors=["ax99pro", "thruster-f"],
     parent_series="axforce-series")
_reg("axforce90", "AXFORCE 90", "Li-Ning", "AXFORCE", "badminton_racket", "AXFORCE 90",
     tier="flagship", user_level="pro", price_min=1580, price_max=1780,
     key_specs=["进攻型", "超硬中杆", "头重", "4U/3U"],
     competitors=["ax100zz"],
     parent_series="axforce-series", successor="axforce80")

_reg("bladex-series", "BLADEX 系列", "Li-Ning", "BLADEX", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("bladex8000", "BLADEX 8000", "Li-Ning", "BLADEX", "badminton_racket", "BLADEX 8000",
     tier="flagship", user_level="pro", price_min=1380, price_max=1580,
     key_specs=["控制型", "适中中杆", "均衡", "4U"],
     competitors=["arc11pro"],
     parent_series="bladex-series")

_reg("halberd-series", "HALBERD 系列", "Li-Ning", "HALBERD", "badminton_racket", "",
     tier="high", user_level="advanced")
_reg("halberd800", "HALBERD 800", "Li-Ning", "HALBERD", "badminton_racket", "HALBERD 800",
     tier="flagship", user_level="pro", price_min=1280, price_max=1480,
     key_specs=["速度型", "硬中杆", "头轻", "4U"],
     competitors=["nf800pro"],
     parent_series="halberd-series")

# ═══ iPhone Series ═══
_reg("iphone16-series", "iPhone 16 系列", "Apple", "iPhone 16", "smartphone", "",
     tier="flagship", user_level="pro", generation="2025")
_reg("iphone16pm", "iPhone 16 Pro Max", "Apple", "iPhone 16", "smartphone", "iPhone 16 Pro Max",
     tier="flagship", user_level="pro", price_min=8999, price_max=9999,
     key_specs=["A18 Pro", "6.9\"", "256GB+"],
     competitors=["s25u", "mate70pro"],
     parent_series="iphone16-series")
_reg("iphone16pro", "iPhone 16 Pro", "Apple", "iPhone 16", "smartphone", "iPhone 16 Pro",
     tier="flagship", user_level="pro", price_min=7999, price_max=8999,
     key_specs=["A18 Pro", "6.3\"", "256GB+"],
     competitors=["s25", "mate70"],
     parent_series="iphone16-series")
_reg("iphone16", "iPhone 16", "Apple", "iPhone 16", "smartphone", "iPhone 16",
     tier="high", user_level="intermediate", price_min=5999, price_max=6999,
     key_specs=["A18", "6.1\"", "128GB+"],
     competitors=["xiaomi15"],
     parent_series="iphone16-series")

# ═══ Android Phones ═══
_reg("mate70-series", "Mate 70 系列", "HUAWEI", "Mate 70", "smartphone", "",
     tier="flagship", user_level="pro")
_reg("mate70pro", "HUAWEI Mate 70 Pro", "HUAWEI", "Mate 70", "smartphone", "Mate 70 Pro",
     tier="flagship", user_level="pro", price_min=6999, price_max=7999,
     key_specs=["麒麟9100", "6.8\"", "512GB+"],
     competitors=["iphone16pm", "s25u"],
     parent_series="mate70-series")

_reg("s25-series", "Galaxy S25 系列", "Samsung", "Galaxy S25", "smartphone", "",
     tier="flagship", user_level="pro")
_reg("s25u", "Samsung Galaxy S25 Ultra", "Samsung", "Galaxy S25", "smartphone", "Galaxy S25 Ultra",
     tier="flagship", user_level="pro", price_min=8999, price_max=10199,
     key_specs=["SD 8 Gen 4", "6.8\"", "256GB+"],
     competitors=["iphone16pm", "mate70pro"],
     parent_series="s25-series")

_reg("xiaomi15-series", "Xiaomi 15 系列", "Xiaomi", "Xiaomi 15", "smartphone", "",
     tier="high", user_level="advanced")
_reg("xiaomi15", "Xiaomi 15 Ultra", "Xiaomi", "Xiaomi 15", "smartphone", "Xiaomi 15 Ultra",
     tier="flagship", user_level="pro", price_min=5999, price_max=6999,
     key_specs=["SD 8 Gen 4", "6.7\"", "512GB+"],
     competitors=["iphone16pm", "s25u"],
     parent_series="xiaomi15-series")

# ═══ NVIDIA GPUs ═══
_reg("rtx50-series", "RTX 50 系列", "NVIDIA", "RTX 50", "graphics_card", "",
     tier="flagship", user_level="pro", generation="2025")
_reg("rtx5090", "RTX 5090", "NVIDIA", "RTX 50", "graphics_card", "RTX 5090",
     tier="flagship", user_level="pro", price_min=14999, price_max=17999,
     key_specs=["32GB", "Blackwell", "PCIe 5.0"],
     competitors=["rx7900xtx"],
     parent_series="rtx50-series")
_reg("rtx5080", "RTX 5080", "NVIDIA", "RTX 50", "graphics_card", "RTX 5080",
     tier="high", user_level="advanced", price_min=8999, price_max=10999,
     key_specs=["16GB", "Blackwell", "PCIe 5.0"],
     competitors=[],
     parent_series="rtx50-series")
_reg("rtx5070ti", "RTX 5070 Ti", "NVIDIA", "RTX 50", "graphics_card", "RTX 5070 Ti",
     tier="mid", user_level="intermediate", price_min=6499, price_max=7499,
     key_specs=["16GB", "Blackwell", "PCIe 5.0"],
     competitors=[],
     parent_series="rtx50-series")


# ═══════════════════════════════════════════════════════════════════════
# Graph traversal API
# ═══════════════════════════════════════════════════════════════════════

def get_node(node_id: str) -> Optional[ProductNode]:
    """Get a product node by ID."""
    return _PRODUCT_GRAPH.get(node_id)


def find_node_by_model(model_name: str) -> Optional[ProductNode]:
    """Find a product node by canonical model name."""
    ml = model_name.lower().strip()
    for node in _PRODUCT_GRAPH.values():
        if node.model.lower() == ml:
            return node
        if ml in node.name.lower():
            return node
    return None


def get_same_series(node_id: str) -> list[ProductNode]:
    """Get all products in the same series."""
    node = _PRODUCT_GRAPH.get(node_id)
    if not node or not node.parent_series:
        return []
    return [
        n for n in _PRODUCT_GRAPH.values()
        if n.parent_series == node.parent_series and n.id != node_id and n.model
    ]


def get_competitors(node_id: str) -> list[ProductNode]:
    """Get direct competitor products."""
    node = _PRODUCT_GRAPH.get(node_id)
    if not node:
        return []
    result = []
    for cid in node.competitors:
        c = _PRODUCT_GRAPH.get(cid)
        if c:
            result.append(c)
    return result


def get_upgrade_path(node_id: str) -> list[ProductNode]:
    """Get upgrade path: successor chain."""
    path = []
    current_id = node_id
    while current_id:
        node = _PRODUCT_GRAPH.get(current_id)
        if not node:
            break
        if node.successor:
            next_node = _PRODUCT_GRAPH.get(node.successor)
            if next_node:
                path.append(next_node)
                current_id = node.successor
            else:
                break
        else:
            break
    return path


def get_same_tier_alternatives(node_id: str) -> list[ProductNode]:
    """Get products with same tier + category from different brands."""
    node = _PRODUCT_GRAPH.get(node_id)
    if not node:
        return []
    return [
        n for n in _PRODUCT_GRAPH.values()
        if n.category == node.category and n.tier == node.tier
        and n.brand != node.brand and n.model
    ]


def get_by_user_level(category: str, user_level: str, top_k: int = 5) -> list[ProductNode]:
    """Get products matching a user level in a category."""
    matches = [
        n for n in _PRODUCT_GRAPH.values()
        if n.category == category and n.user_level == user_level and n.model
    ]
    matches.sort(key=lambda x: x.price_min)
    return matches[:top_k]


def traverse_graph(node_id: str, depth: int = 1) -> dict:
    """Traverse the product graph and return structured relationships."""
    node = _PRODUCT_GRAPH.get(node_id)
    if not node:
        return {}

    result = {
        "node": {
            "id": node.id, "name": node.name, "brand": node.brand,
            "series": node.series, "category": node.category, "model": node.model,
            "tier": node.tier, "user_level": node.user_level,
            "price_range": f"¥{node.price_min:,.0f} - ¥{node.price_max:,.0f}",
            "key_specs": node.key_specs,
        },
        "same_series": [{"id": n.id, "name": n.name, "price_range": f"¥{n.price_min:,.0f}-¥{n.price_max:,.0f}"}
                       for n in get_same_series(node_id)],
        "competitors": [{"id": n.id, "name": n.name, "brand": n.brand}
                       for n in get_competitors(node_id)],
        "upgrades": [{"id": n.id, "name": n.name} for n in get_upgrade_path(node_id)],
    }

    if depth > 1:
        result["alternatives"] = [
            {"id": n.id, "name": n.name, "brand": n.brand}
            for n in get_same_tier_alternatives(node_id)[:5]
        ]

    return result


def suggest_similar(node_id: str, top_k: int = 5) -> list[dict]:
    """Suggest similar products using graph relationships.

    Priority: same series > competitors > same tier alternatives > same category.
    """
    node = _PRODUCT_GRAPH.get(node_id)
    if not node:
        return []

    suggestions: list[dict] = []
    seen: set[str] = {node_id}

    def _add(n: ProductNode, reason: str):
        if n.id not in seen and len(suggestions) < top_k:
            seen.add(n.id)
            suggestions.append({
                "id": n.id, "name": n.name, "brand": n.brand,
                "category": n.category, "price_min": n.price_min, "price_max": n.price_max,
                "tier": n.tier, "reason": reason,
            })

    # 1. Same series (closest match)
    for n in get_same_series(node_id):
        _add(n, f"同系列: {node.series}")

    # 2. Competitors
    for n in get_competitors(node_id):
        _add(n, "竞品对比")

    # 3. Same tier, different brand
    for n in get_same_tier_alternatives(node_id):
        _add(n, f"同级别/{n.brand}")

    # 4. Same category, same user level
    for n in get_by_user_level(node.category, node.user_level, top_k=10):
        _add(n, f"同级别/{node.user_level}")

    return suggestions


def get_graph_stats() -> dict:
    """Get knowledge graph statistics."""
    categories = set(n.category for n in _PRODUCT_GRAPH.values())
    brands = set(n.brand for n in _PRODUCT_GRAPH.values())
    series_nodes = [n for n in _PRODUCT_GRAPH.values() if n.parent_series]
    product_nodes = [n for n in _PRODUCT_GRAPH.values() if n.model]
    return {
        "total_nodes": len(_PRODUCT_GRAPH),
        "product_nodes": len(product_nodes),
        "series_nodes": len(series_nodes),
        "categories": len(categories),
        "brands": len(brands),
        "with_competitors": sum(1 for n in _PRODUCT_GRAPH.values() if n.competitors),
    }
