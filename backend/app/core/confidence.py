"""Confidence scoring for product recommendations and answers.

Computes a 0-100 confidence score for every EVA response based on:
  - Number of corroborating sources
  - Data freshness
  - Retrieval relevance
  - Source authority (official > community > simulated)

Usage:
    from app.core.confidence import ConfidenceScorer

    scorer = ConfidenceScorer()
    score = scorer.compute(sources=3, freshness_days=30, relevance=0.85, authority="official")
"""

from dataclasses import dataclass


@dataclass
class ConfidenceBreakdown:
    """Detailed confidence breakdown."""
    sources_score: float       # 0-40: based on number of corroborating sources
    freshness_score: float     # 0-30: based on how recent the data is
    relevance_score: float     # 0-20: based on retrieval match quality
    authority_score: float     # 0-10: based on source authority
    total: float               # 0-100

    def as_dict(self) -> dict:
        return {
            "sources_score": round(self.sources_score, 1),
            "freshness_score": round(self.freshness_score, 1),
            "relevance_score": round(self.relevance_score, 1),
            "authority_score": round(self.authority_score, 1),
            "total": round(self.total, 1),
        }


AUTHORITY_WEIGHTS = {
    "official": 10.0,
    "api": 9.0,
    "database": 8.0,
    "manual": 7.0,
    "rag": 6.0,
    "community": 3.0,
    "simulated": 0.0,
    "unknown": 1.0,
}


def _freshness_score(age_days: int | None) -> float:
    """Score freshness: 30=max, 90=half, 180=low, 365=zero."""
    if age_days is None:
        return 0.0  # Unknown → no freshness credit
    if age_days <= 7:
        return 30.0
    if age_days <= 30:
        return 25.0
    if age_days <= 90:
        return 20.0
    if age_days <= 180:
        return 10.0
    if age_days <= 365:
        return 5.0
    return 1.0


def _sources_score(num_sources: int) -> float:
    """Score based on number of unique corroborating sources."""
    if num_sources >= 4:
        return 40.0
    if num_sources == 3:
        return 35.0
    if num_sources == 2:
        return 25.0
    if num_sources == 1:
        return 15.0
    return 0.0


def _relevance_score(relevance: float) -> float:
    """Score based on retrieval relevance (0.0-1.0)."""
    return min(relevance * 20.0, 20.0)


def _authority_score(authority_type: str) -> float:
    """Score based on source authority."""
    return AUTHORITY_WEIGHTS.get(authority_type, 1.0)


class ConfidenceScorer:
    """Computes overall confidence score for a response."""

    @staticmethod
    def compute(
        sources: int = 0,
        freshness_days: int | None = None,
        relevance: float = 0.0,
        authority: str = "unknown",
    ) -> float:
        """Compute overall confidence score (0-100)."""
        s = _sources_score(sources)
        f = _freshness_score(freshness_days)
        r = _relevance_score(relevance)
        a = _authority_score(authority)
        return round(s + f + r + a, 1)

    @staticmethod
    def compute_with_breakdown(
        sources: int = 0,
        freshness_days: int | None = None,
        relevance: float = 0.0,
        authority: str = "unknown",
    ) -> ConfidenceBreakdown:
        """Compute confidence with detailed breakdown."""
        s = _sources_score(sources)
        f = _freshness_score(freshness_days)
        r = _relevance_score(relevance)
        a = _authority_score(authority)
        return ConfidenceBreakdown(
            sources_score=s,
            freshness_score=f,
            relevance_score=r,
            authority_score=a,
            total=round(s + f + r + a, 1),
        )

    @staticmethod
    def format(score: float) -> str:
        """Human-readable confidence with warning if low."""
        if score >= 90:
            return f"🟢 可信度：{score:.0f}%"
        if score >= 70:
            return f"🟡 可信度：{score:.0f}%"
        if score > 0:
            return f"🟠 可信度：{score:.0f}% — 该信息可信度较低，建议进一步确认"
        return "🔴 无法验证 — 未找到可靠信息来源"

    @staticmethod
    def get_warning(score: float) -> str | None:
        """Return warning text if confidence is low, None otherwise."""
        if score == 0:
            return "当前知识库未找到相关信息，无法确认该数据真实性。"
        if score < 70:
            return "该信息可信度较低，建议进一步确认。"
        return None
