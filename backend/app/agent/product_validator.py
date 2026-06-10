"""Product Validator — hard constraint enforcement for search results.

Ensures every search result matches the user's detected intent:
  - Brand consistency: if user said YONEX, reject Apple/Samsung/etc.
  - Category consistency: if user wants badminton racket, reject smartphones/laptops
  - Model consistency: if user specified exact model, prioritize exact matches

This is the FINAL GATE before results reach the user. No exceptions.

Usage:
    from app.agent.product_validator import validate_and_filter

    filtered = validate_and_filter(entity, search_results)
    # Only results matching brand + category constraints pass through
"""

from dataclasses import dataclass, field
from typing import Optional

from app.api.v1.admin import append_log


# ═══════════════════════════════════════════════════════════════════════
# Validation result
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class ValidationReport:
    """Report from validating search results against entity constraints."""
    total_input: int
    total_accepted: int
    total_rejected: int
    rejections: list[dict] = field(default_factory=list)
    entity: Optional[dict] = None

    @property
    def acceptance_rate(self) -> float:
        if self.total_input == 0:
            return 0.0
        return self.total_accepted / self.total_input


# ═══════════════════════════════════════════════════════════════════════
# Category distance — how far apart are two categories
# ═══════════════════════════════════════════════════════════════════════

# Groups of related categories that are "close enough" for fallback
_CATEGORY_GROUPS: list[set[str]] = [
    {"smartphone", "tablet"},
    {"laptop", "tablet"},
    {"graphics_card", "cpu", "monitor", "laptop"},
    {"headphone"},
    {"smartwatch", "smartphone"},
    {"gaming_console"},
    {"tv", "monitor"},
    {"camera"},
    {"keyboard", "mouse"},
    {"shoe", "running_shoe", "badminton_shoe", "basketball"},
    {"skincare"},
    {"home_appliance"},
    # Sports equipment — tightly grouped
    {"badminton_racket", "badminton_shuttlecock", "badminton_shoe", "tennis_racket"},
    {"basketball", "football"},
    {"fitness"},
    {"bicycle"},
]

_CAT_GROUP_MAP: dict[str, set[str]] = {}
for _grp in _CATEGORY_GROUPS:
    for _cat in _grp:
        _CAT_GROUP_MAP[_cat] = _grp


def _are_categories_compatible(cat1: str, cat2: str) -> bool:
    """Check if two categories are in the same group (compatible)."""
    if cat1 == cat2:
        return True
    if not cat1 or not cat2:
        return True  # Unknown categories → allow (no constraint)
    grp1 = _CAT_GROUP_MAP.get(cat1, {cat1})
    grp2 = _CAT_GROUP_MAP.get(cat2, {cat2})
    return bool(grp1 & grp2)


def _category_distance(cat1: str, cat2: str) -> float:
    """Return 0.0 (same) to 1.0 (completely different) for two categories."""
    if cat1 == cat2:
        return 0.0
    if _are_categories_compatible(cat1, cat2):
        return 0.3  # Related but not same
    return 1.0  # Completely different


# ═══════════════════════════════════════════════════════════════════════
# Main validation function
# ═══════════════════════════════════════════════════════════════════════

def validate_and_filter(
    entity,  # ProductEntity from product_alias_db
    results: list[dict],
    strict_brand: bool = True,
    strict_category: bool = True,
) -> tuple[list[dict], ValidationReport]:
    """Filter search results to only those matching entity constraints.

    Args:
        entity: ProductEntity with detected brand/category/model
        results: Search results to validate
        strict_brand: If True, reject results with different brand
        strict_category: If True, reject results from different category group

    Returns:
        (filtered_results, validation_report)
    """
    if not entity or not entity.is_valid or entity.confidence < 0.4:
        # No strong entity detected — pass all results through
        report = ValidationReport(
            total_input=len(results),
            total_accepted=len(results),
            total_rejected=0,
            entity=entity.to_dict() if entity else None,
        )
        return results, report

    accepted: list[dict] = []
    rejections: list[dict] = []

    entity_brand = (entity.brand or "").lower()
    entity_category = (entity.category or "").lower()
    entity_product = (entity.product or "").lower()
    allowed_brands = {entity_brand} | {a.lower() for a in (entity.brand_aliases or [])}

    for r in results:
        result_name = (r.get("name") or r.get("title", "")).lower()
        result_brand = (r.get("brand") or "").lower()
        result_category = (r.get("category") or "").lower()
        result_source = r.get("source", r.get("search_layer", ""))

        rejection_reasons: list[str] = []

        # ── Brand check ──
        if strict_brand and entity_brand and result_brand:
            # Check if result brand matches or result name contains brand
            brand_in_name = any(b in result_name for b in allowed_brands if b)
            brand_matches = result_brand in allowed_brands

            if not brand_matches and not brand_in_name:
                rejection_reasons.append(
                    f"品牌不匹配: 期望={entity.brand}, 实际={r.get('brand', '未知')}"
                )

        # ── Category check ──
        if strict_category and entity_category and entity_category != "general" and result_category:
            if not _are_categories_compatible(entity_category, result_category):
                rejection_reasons.append(
                    f"分类不匹配: 期望={entity.category}, 实际={result_category}"
                )

        # ── Model check (loose) ──
        if entity_product and entity.confidence >= 0.8:
            # Check if result name contains key model terms
            model_terms = entity_product.replace("-", " ").replace("_", " ").lower().split()
            # Filter out common words
            significant_terms = [t for t in model_terms if len(t) > 2 and t not in ("pro", "max", "ultra")]
            if significant_terms:
                term_match = any(t in result_name for t in significant_terms)
                if not term_match:
                    rejection_reasons.append(
                        f"型号不匹配: 期望包含={significant_terms[:3]}"
                    )

        if rejection_reasons:
            rejections.append({
                "product": r.get("name", r.get("title", "未知")),
                "brand": r.get("brand", ""),
                "category": r.get("category", ""),
                "reasons": rejection_reasons,
                "source": result_source,
            })
        else:
            # Boost confidence for matching results
            r_copy = dict(r)
            if entity_brand and entity_category:
                r_copy["entity_match"] = True
                r_copy["confidence"] = min(
                    (r.get("confidence", 50) or 50) * 1.3, 98.0
                )
            accepted.append(r_copy)

    # Log rejections
    if rejections:
        reasons_summary = {}
        for rej in rejections:
            for reason in rej["reasons"]:
                reasons_summary[reason] = reasons_summary.get(reason, 0) + 1
        append_log(
            "WARN" if len(accepted) == 0 else "INFO",
            f"Validator: {len(accepted)}/{len(results)} accepted, "
            f"{len(rejections)} rejected. Reasons: {reasons_summary}"
        )

    report = ValidationReport(
        total_input=len(results),
        total_accepted=len(accepted),
        total_rejected=len(rejections),
        rejections=rejections,
        entity=entity.to_dict() if entity else None,
    )

    return accepted, report


def validate_single(entity, result: dict) -> tuple[bool, float, str]:
    """Validate a single search result. Returns (is_valid, adjusted_confidence, reason)."""
    if not entity or not entity.is_valid:
        return True, result.get("confidence", 50), "no constraint"

    entity_brand = (entity.brand or "").lower()
    entity_category = (entity.category or "").lower()
    result_name = (result.get("name") or result.get("title", "")).lower()
    result_brand = (result.get("brand") or "").lower()
    result_category = (result.get("category") or "").lower()
    result_conf = result.get("confidence", 50) or 50

    # Brand penalty
    if entity_brand and result_brand:
        allowed_brands = {entity_brand} | {a.lower() for a in (entity.brand_aliases or [])}
        brand_in_name = any(b in result_name for b in allowed_brands if b)
        if result_brand not in allowed_brands and not brand_in_name:
            return False, 0.0, f"品牌不匹配"

    # Category penalty
    if entity_category and entity_category != "general" and result_category:
        dist = _category_distance(entity_category, result_category)
        if dist >= 1.0:
            return False, 0.0, f"跨品类: {entity_category} vs {result_category}"
        elif dist > 0:
            result_conf *= 0.5  # Penalize but don't reject

    return True, result_conf, "ok"
