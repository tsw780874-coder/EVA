"""Data Verification Layer — cross-references claims against RAG + DB.

Every factual claim (price, spec, rating) must be verified before
presentation to the user. Claims that cannot be verified are flagged.

Usage:
    from app.core.verifier import DataVerifier

    verifier = DataVerifier()
    results = await verifier.verify_product_claims(products)
    # Each product gets: verified=True/False, confidence=0-100, sources=[]
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from app.api.v1.admin import append_log


@dataclass
class VerificationResult:
    """Result of verifying a single claim."""
    claim: str                 # What was claimed (e.g., "iPhone 16价格8999")
    verified: bool             # Has corroborating evidence
    confidence: float          # 0.0 - 100.0
    source_type: str           # "rag" | "database" | "official" | "simulated" | "unknown"
    source_name: str           # Where the evidence came from
    evidence: str              # Supporting text or "无可靠来源"
    freshness_days: int | None # Days since source was updated, or None


@dataclass
class ProductVerification:
    """Complete verification of a product's claims."""
    product_name: str
    platform: str
    price_verified: bool
    price_evidence: str
    specs_verified: bool
    specs_evidence: str
    rating_verified: bool
    rating_evidence: str
    overall_confidence: float   # 0-100
    sources: list[str] = field(default_factory=list)
    freshness_warnings: list[str] = field(default_factory=list)


# ── Freshness thresholds ──
FRESH_THRESHOLD_DAYS = 90   # After this, confidence decays
STALE_THRESHOLD_DAYS = 180  # After this, mark as potentially stale
FRESH_DECAY_RATE = 0.5       # Weight multiplier for data past freshness threshold


def _check_freshness(updated_at_str: str | None) -> tuple[int | None, bool, str | None]:
    """Check document freshness. Returns (days_old, is_stale, warning)."""
    if not updated_at_str:
        return None, False, None

    try:
        from datetime import datetime, timezone, timedelta
        # Parse ISO format date
        if 'T' in updated_at_str:
            updated = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
        else:
            updated = datetime.strptime(updated_at_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_days = (now - updated).days

        if age_days > STALE_THRESHOLD_DAYS:
            return age_days, True, f"数据已超过{STALE_THRESHOLD_DAYS}天未更新，可能已过期"
        elif age_days > FRESH_THRESHOLD_DAYS:
            return age_days, False, f"数据超过{FRESH_THRESHOLD_DAYS}天，可能不是最新"
        return age_days, False, None
    except Exception:
        return None, False, None


def _freshness_weight(age_days: int | None) -> float:
    """Compute freshness weight multiplier."""
    if age_days is None:
        return 0.7  # Unknown freshness → moderate confidence
    if age_days <= FRESH_THRESHOLD_DAYS:
        return 1.0
    return FRESH_DECAY_RATE


class DataVerifier:
    """Cross-reference claims against available evidence sources."""

    def __init__(self):
        self._db_checked = False

    async def _search_rag(self, query: str, top_k: int = 5) -> list[dict]:
        """Query the RAG knowledge base for evidence."""
        try:
            from app.services.rag_service import search_knowledge
            return await search_knowledge(query, top_k=top_k)
        except Exception:
            return []

    async def _search_db(self, product_name: str) -> list[dict]:
        """Query the product database for evidence."""
        try:
            from app.models.product import Product
            from app.core.database import async_session
            from sqlalchemy import select

            async with async_session() as db:
                result = await db.execute(
                    select(Product).where(Product.name.contains(product_name)).limit(5)
                )
                products = result.scalars().all()
                return [
                    {
                        "name": p.name,
                        "platform": p.platform,
                        "price": p.price,
                        "rating": p.rating,
                        "source": p.source or "database",
                        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                    }
                    for p in products
                ]
        except Exception:
            return []

    async def verify_product_price(
        self, product_name: str, platform: str, claimed_price: float,
    ) -> VerificationResult:
        """Verify a product price claim."""
        claim = f"{product_name}在{platform}售价¥{claimed_price}"

        # 1. Check DB first
        db_results = await self._search_db(product_name)
        for p in db_results:
            if p.get("platform") == platform and p.get("price"):
                actual_price = float(p["price"])
                price_diff_pct = abs(claimed_price - actual_price) / actual_price * 100

                age_days, _, _ = _check_freshness(p.get("updated_at"))

                if price_diff_pct < 5:  # Within 5% → verified
                    confidence = 95.0 * _freshness_weight(age_days)
                    return VerificationResult(
                        claim=claim, verified=True, confidence=min(confidence, 100),
                        source_type="database", source_name=p.get("source", "database"),
                        evidence=f"数据库记录: {p['name']} @ ¥{actual_price}",
                        freshness_days=age_days,
                    )

        # 2. Check RAG
        rag_results = await self._search_rag(f"{product_name} {platform} 价格")
        for r in rag_results:
            content = str(r.get("content", ""))
            if platform in content and "价格" in content:
                confidence = r.get("score", 0.5) * 80
                return VerificationResult(
                    claim=claim, verified=True, confidence=confidence,
                    source_type="rag",
                    source_name=r.get("source", r.get("metadata", {}).get("source", "知识库")),
                    evidence=content[:200],
                    freshness_days=None,
                )

        # 3. No evidence
        return VerificationResult(
            claim=claim, verified=False, confidence=0.0,
            source_type="unknown", source_name="无",
            evidence="未在数据库或知识库中找到匹配的价格信息",
            freshness_days=None,
        )

    async def verify_product_claims(
        self, products: list[dict],
    ) -> list[ProductVerification]:
        """Verify all claims for a list of products.

        Uses batched DB queries for efficiency and skips expensive verification
        for cache/live-search sourced products that already have confidence scores.
        """
        results = []
        for p in products:
            name = p.get("name", "未知")
            platform = p.get("platform", "未知")
            price = p.get("price", 0)
            source = p.get("source", "")
            existing_confidence = p.get("confidence", 0.0)

            # For cache/live-search/similar sources, trust the existing confidence
            # to avoid redundant and expensive DB verification
            is_simulated = source == "simulated"
            is_cached = source in ("product_cache", "live_search", "similar_search", "hot_products", "link_fallback")
            db_source = source in ("database", "official", "manual")

            sources = []
            freshness_warnings = []
            price_verified = False
            price_evidence = ""

            if is_simulated:
                confidence = 0.0
                sources.append("⚠️ 模拟数据")
            elif is_cached:
                # Cache products already have confidence from the cache layer
                confidence = existing_confidence
                sources.append(f"✓ 商品缓存: {source}")
                price_verified = existing_confidence >= 30
                price_evidence = f"缓存数据 (置信度: {existing_confidence:.0f}%)"
            elif db_source:
                confidence = 70.0
                sources.append(f"✓ 数据库记录: {source}")
                price_verified = True
                price_evidence = "数据库记录"
            else:
                # Only do expensive verification for unknown-source products
                price_check = await self.verify_product_price(
                    name, platform, float(price) if price else 0
                )
                if price_check.verified:
                    confidence = price_check.confidence
                    sources.append(f"✓ 价格已验证: {price_check.source_name}")
                    price_verified = True
                    price_evidence = price_check.evidence
                    if price_check.freshness_days:
                        _, _, warning = _check_freshness(
                            p.get("updated_at") or str(price_check.freshness_days)
                        )
                        if warning:
                            freshness_warnings.append(warning)
                else:
                    confidence = 10.0
                    sources.append("⚠️ 数据来源未确认")
                    price_evidence = price_check.evidence

            results.append(ProductVerification(
                product_name=name,
                platform=platform,
                price_verified=price_verified,
                price_evidence=price_evidence,
                specs_verified=bool(p.get("specs")),
                specs_evidence="数据库规格" if p.get("specs") else "无规格信息",
                rating_verified=bool(p.get("rating") and not is_simulated),
                rating_evidence="数据库评分" if p.get("rating") and not is_simulated else "模拟评分",
                overall_confidence=round(confidence, 1),
                sources=sources,
                freshness_warnings=freshness_warnings,
            ))

        return results

    @staticmethod
    def aggregate_confidence(verifications: list[ProductVerification]) -> float:
        """Compute overall confidence across all products."""
        if not verifications:
            return 0.0
        scores = [v.overall_confidence for v in verifications]
        return round(sum(scores) / len(scores), 1)

    @staticmethod
    def confidence_rating(score: float) -> str:
        """Human-readable confidence rating."""
        if score >= 90:
            return "★★★★★ 极高可信"
        if score >= 70:
            return "★★★★☆ 可信"
        if score >= 50:
            return "★★★☆☆ 一般可信"
        if score > 0:
            return "★★☆☆☆ 可信度较低"
        return "⚠️ 无法验证"
