"""Shared type definitions for the EVA Hybrid AI system."""

from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class SourceType(str, Enum):
    """Five information sources available to EVA."""
    RAG = "rag"             # Knowledge base retrieval (Milvus + BM25)
    WEB = "web"             # Real-time web search
    MEMORY = "memory"       # Historical conversation memory
    TOOL = "tool"           # Database / API / computation
    REASONING = "reasoning" # Logical inference / deduction


class QuestionType(str, Enum):
    """Classification of user questions."""
    FACTUAL = "factual"             # Fact lookup → RAG / Web
    TIME_SENSITIVE = "time_sensitive"  # Latest info → Web (priority)
    HISTORICAL = "historical"       # Past context → Memory
    COMPUTATIONAL = "computational" # Calculation / data → Tool
    COMPLEX = "complex"             # Multi-step → Decompose + reason
    COMPARATIVE = "comparative"     # Compare items → RAG + Web
    PROCEDURAL = "procedural"       # How-to / guide → RAG + Reasoning


class ConfidenceLevel(str, Enum):
    """Confidence level for response."""
    HIGH = "high"       # Multiple corroborating sources, verified data
    MEDIUM = "medium"   # Single source or moderate agreement
    LOW = "low"         # Weak signal, uncertain data


@dataclass
class SourceEvidence:
    """Evidence from a single information source."""
    source: SourceType
    content: str                        # The raw content retrieved
    relevance_score: float = 0.0        # 0.0 - 1.0
    freshness_days: int | None = None   # Age of the data in days
    authority: str = "unknown"          # "official" | "community" | "rag" | "simulated"
    url: str | None = None              # Source URL if applicable
    retrieved_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class SourceResult:
    """Result from querying an information source."""
    source: SourceType
    success: bool                       # Did we get useful data?
    evidence: list[SourceEvidence] = field(default_factory=list)
    error: str | None = None           # Error message if failed
    latency_ms: float = 0.0            # How long the query took
    escalated: bool = False            # Was query escalated/rewritten?


@dataclass
class HybridResult:
    """Final result from the Hybrid AI pipeline."""
    # Core answer
    answer: str                                 # The main answer text
    answer_summary: str = ""                    # One-line summary

    # Source tracking
    sources_used: list[SourceType] = field(default_factory=list)
    primary_source: SourceType | None = None    # Which source provided the answer

    # Confidence
    confidence: float = 0.0                     # 0-100
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW
    confidence_breakdown: dict = field(default_factory=dict)

    # Evidence trail
    all_evidence: list[SourceEvidence] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)

    # Conflict info
    conflicts_detected: bool = False
    conflict_details: list[str] = field(default_factory=list)

    # Warnings
    warnings: list[str] = field(default_factory=list)
    hallucination_checks_passed: bool = True

    # Metadata
    question_type: QuestionType | None = None
    total_latency_ms: float = 0.0
    escalated: bool = False                     # Did we need to escalate?

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "answer_summary": self.answer_summary,
            "sources_used": [s.value for s in self.sources_used],
            "primary_source": self.primary_source.value if self.primary_source else None,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "confidence_breakdown": self.confidence_breakdown,
            "citations": self.citations,
            "conflicts_detected": self.conflicts_detected,
            "conflict_details": self.conflict_details,
            "warnings": self.warnings,
            "hallucination_checks_passed": self.hallucination_checks_passed,
            "question_type": self.question_type.value if self.question_type else None,
            "total_latency_ms": self.total_latency_ms,
            "escalated": self.escalated,
        }


@dataclass
class SourcePlan:
    """Plan for which sources to query and in what order."""
    question_type: QuestionType
    primary_sources: list[SourceType]     # Must-query sources
    fallback_sources: list[SourceType]    # Query if primary fails
    requires_web: bool = False            # Force web search?
    requires_tool: bool = False           # Force tool execution?
    requires_memory: bool = False         # Check memory?
    requires_decomposition: bool = False  # Multi-step reasoning needed?
    escalation_threshold: float = 0.3     # Min relevance to accept (0-1)
