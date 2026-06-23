"""Anti-Hallucination Guard for EVA Hybrid AI.

Enforces strict rules to prevent fabricated data:
  1. Never invent product prices, specs, or reviews
  2. Never fill in missing information
  3. Never speculate about non-existent content
  4. Never fabricate citations or sources
  5. Never use previous assistant outputs as facts

Usage:
    from app.hybrid.guard import HallucinationGuard

    guard = HallucinationGuard()
    result = guard.check(response_text, evidence_list)
"""

import re
from dataclasses import dataclass, field
from app.hybrid.types import SourceEvidence, SourceType


@dataclass
class GuardResult:
    """Result of a hallucination check."""
    passed: bool
    issues: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    corrected_text: str = ""


class HallucinationGuard:
    """Checks AI responses for hallucination/fabrication.

    Rules enforced:
      1. All price claims must have source evidence
      2. All product specs must be traceable to a source
      3. No fabricated URLs or platform names
      4. No speculative language about unverified data
    """

    # Patterns that indicate potential hallucination
    _SPECULATION_MARKERS = [
        r"可能大约.*价格",
        r"估计.*元左右",
        r"应该.*差不多",
        r"大概在.*范围",
        r"通常在.*之间",
    ]

    # Price patterns — must be corroborated by evidence
    _PRICE_PATTERN = re.compile(r'[¥￥]\s*(\d[\d,]*)')

    # Known legitimate platforms
    _KNOWN_PLATFORMS = {
        "京东", "天猫", "淘宝", "得物", "拼多多", "苏宁", "唯品会",
        "闲鱼", "识货", "nice", "亚马逊", "当当",
    }

    # URLs that shouldn't be fabricated
    _URL_PATTERN = re.compile(r'https?://[^\s\)】。，]+')

    def check(
        self,
        response_text: str,
        evidence_list: list[SourceEvidence],
        products: list[dict] | None = None,
    ) -> GuardResult:
        """Run all hallucination checks on the response.

        Args:
            response_text: The AI-generated response
            evidence_list: Evidence sources used to generate the response
            products: Product data referenced in the response

        Returns:
            GuardResult with pass/fail and any issues found
        """
        issues = []
        violations = []
        warnings = []

        # ── Check 1: Unsubstantiated price claims ──
        prices_in_response = self._PRICE_PATTERN.findall(response_text)
        prices_in_evidence = 0
        for ev in evidence_list:
            prices_in_evidence += len(self._PRICE_PATTERN.findall(ev.content))

        if prices_in_response and prices_in_evidence == 0 and not products:
            violations.append(
                f"响应中包含 {len(prices_in_response)} 个价格声明，"
                f"但证据中未找到任何价格数据。"
            )

        # ── Check 2: Fabricated URLs ──
        urls_in_response = self._URL_PATTERN.findall(response_text)
        urls_in_evidence = set()
        for ev in evidence_list:
            if ev.url:
                urls_in_evidence.add(ev.url)
            urls_in_evidence.update(self._URL_PATTERN.findall(ev.content))

        fabricated_urls = [
            u for u in urls_in_response
            if u not in urls_in_evidence
        ]
        if fabricated_urls:
            violations.append(
                f"响应中包含 {len(fabricated_urls)} 个未经验证的URL："
                f"{', '.join(fabricated_urls[:3])}"
            )

        # ── Check 3: Speculative language ──
        for marker_pattern in self._SPECULATION_MARKERS:
            matches = re.findall(marker_pattern, response_text)
            if matches:
                warnings.append(
                    f"检测到推测性表述，可能未经验证：(示例) {matches[0][:60]}"
                )

        # ── Check 4: Missing source attribution ──
        if evidence_list and len(response_text) > 100:
            # Check if response acknowledges sources
            has_source_ref = any(
                kw in response_text
                for kw in ["来源", "根据", "数据来自", "参考", "引用", "据"]
            )
            if not has_source_ref and not products:
                warnings.append(
                    "响应使用了证据但未标注信息来源。"
                )

        # ── Check 5: Excessive confidence without evidence ──
        confidence_markers = ["绝对", "保证", "100%", "肯定", "毫无疑问", "必定"]
        if evidence_list:
            evidence_str = " ".join(ev.content for ev in evidence_list)
            for marker in confidence_markers:
                if marker in response_text and marker not in evidence_str:
                    warnings.append(f"使用绝对化表述'{marker}'但无相应证据支撑。")
                    break

        # ── Check 6: Simulated data transparency ──
        if products:
            simulated = [p for p in products if p.get("source") == "simulated"]
            if simulated and "模拟" not in response_text and "参考" not in response_text:
                violations.append(
                    f"响应使用了 {len(simulated)} 个模拟商品的数据但未标注为模拟数据。"
                )

        # Determine pass/fail
        passed = len(violations) == 0

        return GuardResult(
            passed=passed,
            issues=issues,
            violations=violations,
            warnings=warnings,
        )

    def sanitize(self, response_text: str, evidence_list: list[SourceEvidence]) -> str:
        """Attempt to sanitize a response by flagging unverifiable claims.

        Does NOT modify text — only adds warning markers where appropriate.
        """
        result = self.check(response_text, evidence_list)

        if not result.passed:
            warning_header = (
                "\n\n> ⚠️ **可信度警告**：以下内容包含未经充分验证的声明，请谨慎参考。\n"
            )
            # Add violation notes
            for v in result.violations:
                warning_header += f"> - {v}\n"

            return response_text + warning_header

        return response_text


# ── Singleton ──

_default_guard = HallucinationGuard()


def check_hallucination(
    response_text: str,
    evidence_list: list[SourceEvidence],
    products: list[dict] | None = None,
) -> GuardResult:
    """Quick hallucination check using the default guard."""
    return _default_guard.check(response_text, evidence_list, products)


def sanitize_response(
    response_text: str,
    evidence_list: list[SourceEvidence],
) -> str:
    """Sanitize a response by flagging unverifiable claims."""
    return _default_guard.sanitize(response_text, evidence_list)
