"""Citation tracking and formatting for trustworthy responses.

Every factual claim in an EVA response must be traceable to a source.
Citations are attached to the final report as a formatted block.

Usage:
    from app.core.citations import Citation, CitationTracker

    tracker = CitationTracker()
    tracker.add("价格数据来自京东官方", source_type="database", source_name="Product DB")
    block = tracker.render()
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Citation:
    """A single citation reference."""
    text: str                    # What is being cited
    source_type: str             # "database" | "rag" | "official" | "api"
    source_name: str             # Human-readable source name
    updated_at: str | None = None  # When the source was last updated
    url: str | None = None       # URL if applicable
    confidence: float = 100.0    # Confidence in this citation (0-100)


class CitationTracker:
    """Collects citations during response generation and renders them."""

    def __init__(self):
        self._citations: list[Citation] = []
        self._has_simulated_data = False

    def add(
        self, text: str, *,
        source_type: str = "unknown",
        source_name: str = "",
        updated_at: str | None = None,
        url: str | None = None,
        confidence: float = 100.0,
    ):
        self._citations.append(Citation(
            text=text, source_type=source_type, source_name=source_name,
            updated_at=updated_at, url=url, confidence=confidence,
        ))

    def mark_simulated(self):
        """Mark that the response contains simulated/placeholder data."""
        self._has_simulated_data = True

    @property
    def has_real_data(self) -> bool:
        return any(
            c.source_type in ("database", "rag", "official", "api")
            for c in self._citations
        )

    @property
    def all_simulated(self) -> bool:
        return self._has_simulated_data and not self.has_real_data

    def render(self) -> str:
        """Generate a formatted citation block in markdown."""
        if not self._citations:
            return ""

        lines = ["", "---", "## 📚 信息来源", ""]

        if self._has_simulated_data:
            lines.append("> ⚠️ **注意：以下部分数据为模拟数据，仅供参考，不反映真实市场价格。**")
            lines.append("")

        # Group by source type
        db_sources = [c for c in self._citations if c.source_type == "database"]
        rag_sources = [c for c in self._citations if c.source_type == "rag"]
        official_sources = [c for c in self._citations if c.source_type == "official"]
        simulated = [c for c in self._citations if c.source_type == "simulated"]
        api_sources = [c for c in self._citations if c.source_type == "api"]

        for label, sources in [
            ("🗄️ 数据库", db_sources),
            ("📖 知识库", rag_sources),
            ("🏛️ 官方来源", official_sources),
            ("🔌 API数据", api_sources),
        ]:
            if sources:
                lines.append(f"**{label}**")
                for c in sources:
                    time_info = f" (更新于 {c.updated_at})" if c.updated_at else ""
                    conf = f" [可信度: {c.confidence:.0f}%]" if c.confidence < 90 else ""
                    url_info = f" — {c.url}" if c.url else ""
                    lines.append(f"- {c.text}{time_info}{conf}{url_info}")
                lines.append("")

        if simulated:
            lines.append("**⚠️ 模拟数据**")
            for c in simulated:
                lines.append(f"- {c.text}")
            lines.append("")

        return "\n".join(lines)

    def render_short(self) -> str:
        """Single-line citation summary for SSE streams."""
        if self._has_simulated_data and not self.has_real_data:
            return "⚠️ 数据来源：模拟数据（非真实市场数据）"

        if not self._citations:
            return ""

        sources = set(c.source_name for c in self._citations if c.source_type != "simulated")
        if sources:
            return f"📚 数据来源：{'、'.join(sources)}"

        if self._has_simulated_data:
            return "⚠️ 数据来源：模拟数据（非真实市场数据）"
        return "⚠️ 无可靠数据来源"
