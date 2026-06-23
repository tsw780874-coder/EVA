"""Conflict Resolver — resolves information conflicts between sources.

Priority: Web > RAG > Memory

When different sources provide conflicting information, this module:
  1. Detects conflicts (same claim, different values)
  2. Applies priority rules to determine the most reliable source
  3. Explicitly documents the conflict and resolution
  4. Never silently picks one — always informs the user

Usage:
    from app.hybrid.conflict_resolver import detect_conflicts, resolve

    conflicts = detect_conflicts(evidence_list)
    resolution = resolve(conflicts)
"""

from app.hybrid.types import SourceEvidence, SourceType


# ═══════════════════════════════════════════════════════════════════════
# Source priority weights (higher = more trusted)
# ═══════════════════════════════════════════════════════════════════════

SOURCE_PRIORITY: dict[SourceType, int] = {
    SourceType.WEB: 100,
    SourceType.TOOL: 85,
    SourceType.RAG: 70,
    SourceType.MEMORY: 40,
    SourceType.REASONING: 20,
}

AUTHORITY_PRIORITY: dict[str, int] = {
    "official": 100,
    "api": 85,
    "database": 75,
    "manual": 65,
    "rag": 55,
    "community": 30,
    "simulated": 0,
    "unknown": 10,
}


def _extract_price_claims(evidence: list[SourceEvidence]) -> dict[str, list[tuple[SourceEvidence, float]]]:
    """Extract price claims from evidence, keyed by product name."""
    import re
    claims: dict[str, list[tuple[SourceEvidence, float]]] = {}

    for ev in evidence:
        content = ev.content
        # Find price patterns: ¥XXX or 价格: XXX
        prices = re.findall(r'[¥￥]\s*([\d,]+\.?\d*)', content)
        # Find product names near prices
        names = re.findall(r'(?:iPhone|iPad|MacBook|AirPods|华为|小米|Galaxy|'
                          r'ThinkPad|YONEX|Victor|天斧|疾光|龙牙|雷霆|神速|'
                          r'手机|笔记本|耳机|球拍|鞋|包)[^\s,，。]*', content)

        for price_str in prices:
            try:
                price = float(price_str.replace(",", ""))
                # Associate with nearest product name
                name = names[0] if names else "未知商品"
                if name not in claims:
                    claims[name] = []
                claims[name].append((ev, price))
            except ValueError:
                pass

    return claims


def detect_conflicts(evidence_list: list[SourceEvidence]) -> list[dict]:
    """Detect conflicts between sources.

    Returns list of conflict descriptions:
        [
            {
                "claim": "iPhone 16价格",
                "values": {"web": 5999, "rag": 5499},
                "resolution": "采用Web数据（最新）",
                "priority_applied": "WEB > RAG",
            }
        ]
    """
    conflicts = []

    # Detect price conflicts
    price_claims = _extract_price_claims(evidence_list)
    for product_name, claims in price_claims.items():
        if len(claims) < 2:
            continue

        # Group by source type
        by_source: dict[SourceType, float] = {}
        for ev, price in claims:
            if ev.source not in by_source:
                by_source[ev.source] = price

        # Check if values differ significantly (>10%)
        values = list(by_source.values())
        if len(values) >= 2:
            max_val = max(values)
            min_val = min(values)
            if max_val > 0 and (max_val - min_val) / max_val > 0.1:
                # Conflict detected!
                resolution_source = _resolve_priority(list(by_source.keys()))
                conflicts.append({
                    "claim": f"{product_name} 价格",
                    "values": {s.value: v for s, v in by_source.items()},
                    "resolution": f"采用 {resolution_source.value} 数据（优先级最高）",
                    "priority_applied": " > ".join(
                        s.value for s in sorted(
                            by_source.keys(),
                            key=lambda s: SOURCE_PRIORITY.get(s, 0),
                            reverse=True,
                        )
                    ),
                })

    return conflicts


def _resolve_priority(sources: list[SourceType]) -> SourceType:
    """Return the highest-priority source."""
    return max(sources, key=lambda s: SOURCE_PRIORITY.get(s, 0))


def resolve(
    conflicts: list[dict],
    evidence_list: list[SourceEvidence],
) -> tuple[list[SourceEvidence], list[str]]:
    """Resolve conflicts and return filtered evidence + resolution notes.

    Applies priority: Web > RAG > Memory

    Args:
        conflicts: List of detected conflicts
        evidence_list: All collected evidence

    Returns:
        (filtered_evidence, resolution_notes)
    """
    if not conflicts:
        return evidence_list, []

    resolution_notes = []

    for conflict in conflicts:
        claim = conflict["claim"]
        resolution = conflict["resolution"]
        priority = conflict["priority_applied"]
        note = f"⚡ 信息冲突：{claim} | 解决：{resolution} | 优先级：{priority}"
        resolution_notes.append(note)

    # Remove lower-priority conflicting evidence
    # (Keep all evidence but flag the conflict in notes)
    # We don't actually remove evidence — we just inform the user

    return evidence_list, resolution_notes


def format_conflict_report(conflicts: list[dict]) -> str:
    """Format conflicts as a human-readable report."""
    if not conflicts:
        return ""

    lines = ["", "### ⚡ 信息冲突说明", ""]
    for c in conflicts:
        lines.append(f"- **{c['claim']}**：")
        lines.append(f"  - 不同来源数据：{c['values']}")
        lines.append(f"  - 解决方式：{c['resolution']}")
        lines.append(f"  - 优先级规则：{c['priority_applied']}")
        lines.append("")

    return "\n".join(lines)
