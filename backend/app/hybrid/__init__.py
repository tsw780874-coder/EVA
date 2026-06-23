"""EVA Hybrid AI System — Multi-Source Intelligent Assistant.

Architecture:
  User Query → Source Selector → [RAG | Web | Memory | Tool | Reasoning]
                           ↓
                    Conflict Resolver
                           ↓
                    Hallucination Guard
                           ↓
                    Output Formatter → Structured Response

The HybridAI engine embodies the 12 rules defined in the EVA system prompt:
  1. Analyze question type → select information sources
  2. Source priority: Web > RAG > Memory > Reasoning
  3. Information insufficient → escalate query (never guess)
  4. Context isolation between conversation turns
  5. Strict anti-hallucination: never fabricate data
  6. Conflict resolution: Web > RAG > Memory
  7. Mandatory output format: Answer + Sources + Confidence
"""

from app.hybrid.core import HybridAI, hybrid_ai
from app.hybrid.types import (
    SourceType,
    QuestionType,
    ConfidenceLevel,
    SourceResult,
    HybridResult,
    SourceEvidence,
)
from app.hybrid.source_selector import select_sources, analyze_question

__all__ = [
    "HybridAI",
    "hybrid_ai",
    "SourceType",
    "QuestionType",
    "ConfidenceLevel",
    "SourceResult",
    "HybridResult",
    "SourceEvidence",
    "select_sources",
    "analyze_question",
]
