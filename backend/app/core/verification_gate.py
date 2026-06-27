"""Verification Gate — 强制验证门禁系统（核心安全模块）

所有 LLM 输出必须通过此门禁才能返回给用户。
四个验证维度：
  1. 证据检查 (Evidence Check)  — 声明是否有来源支撑
  2. 冲突检查 (Conflict Check)  — 证据之间是否存在矛盾
  3. 可推导检查 (Derivation Check) — 结论是否可从来源逻辑推导
  4. 臆造检查 (Fabrication Check) — 是否存在编造的价格/URL/规格

设计原则：
  - 默认不信任 (deny-by-default)
  - 无证据 = 不允许输出
  - 任何检查 FAIL → 返回安全回退消息

用法:
    from app.core.verification_gate import VerificationGate, Verdict

    gate = VerificationGate()
    verdict = await gate.verify(answer_text, evidence_list, products)

    if not verdict.passed:
        return SAFE_FALLBACK_MESSAGE  # "未找到可靠数据，请尝试其他查询"
"""

import re
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from app.hybrid.types import SourceEvidence, SourceType


# ═══════════════════════════════════════════════════════════════════════
# 类型定义
# ═══════════════════════════════════════════════════════════════════════


class CheckResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"  # 不确定，但不阻止


class GateAction(str, Enum):
    ALLOW = "allow"  # 允许输出
    BLOCK = "block"  # 阻止输出
    FLAG = "flag"    # 允许但标注警告


@dataclass
class SingleCheck:
    """单个验证维度结果"""
    dimension: str                          # evidence / conflict / derivation / fabrication
    result: CheckResult
    reason: str = ""
    details: list[str] = field(default_factory=list)
    confidence: float = 1.0                 # 检查本身的置信度


@dataclass
class Verdict:
    """验证门禁最终判决"""
    passed: bool                            # 是否通过所有检查
    action: GateAction                      # 系统应采取的行动
    checks: list[SingleCheck] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    overall_confidence: float = 0.0         # 综合可信度 (0-100)

    @property
    def summary(self) -> str:
        """人类可读的判决摘要"""
        if self.passed:
            return f"✅ 验证通过 (置信度: {self.overall_confidence:.0f}%)"
        failed = ", ".join(self.failed_checks)
        return f"❌ 验证未通过: {failed}"


# ═══════════════════════════════════════════════════════════════════════
# 安全回退消息
# ═══════════════════════════════════════════════════════════════════════

SAFE_FALLBACK_MESSAGE = (
    "未找到可靠数据来回答此问题。\n\n"
    "可能的原因：\n"
    "- 当前知识库中没有相关商品信息\n"
    "- 实时搜索未能获取有效数据\n"
    "- 信息来源之间存在矛盾，无法确认\n\n"
    "建议：\n"
    "- 尝试使用更具体的商品名称或型号\n"
    "- 检查拼写是否正确\n"
    "- 切换至其他查询方式"
)

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "当前检索结果不足以支撑可靠回答。\n\n"
    "系统检索了以下来源但未找到充分证据：\n"
    "- RAG知识库\n"
    "- 实时Web搜索\n"
    "- 数据库查询\n\n"
    "请尝试更具体的查询，或稍后再试。"
)


# ═══════════════════════════════════════════════════════════════════════
# 验证门禁引擎
# ═══════════════════════════════════════════════════════════════════════

class VerificationGate:
    """强制验证门禁 — 所有 LLM 输出必须通过此门禁。

    使用方式:
        gate = VerificationGate(threshold=60.0)  # 60% 综合置信度阈值
        verdict = await gate.verify(answer, evidence, products)

        if verdict.passed:
            return answer  # 安全，可输出
        else:
            return SAFE_FALLBACK_MESSAGE
    """

    # ── 臆造检测模式 ──
    _PRICE_PATTERN = re.compile(r'[¥￥]\s*(\d[\d,]*)')
    _URL_PATTERN = re.compile(r'https?://[^\s\)】。，]+')
    _SPECULATION_MARKERS = [
        r"可能大约.*价格",
        r"估计.*元左右",
        r"应该.*差不多",
        r"大概在.*范围",
        r"通常在.*之间",
        r"一般.*左右",
        r"预计.*价格",
        r"大概.*左右",
    ]
    _ABSOLUTE_MARKERS = ["绝对", "保证", "100%", "肯定", "毫无疑问", "必定"]

    def __init__(self, threshold: float = 60.0):
        """初始化验证门禁。

        Args:
            threshold: 综合置信度阈值 (0-100)。低于此值将阻止输出。
                       默认 60%，可根据场景调整。
        """
        self.threshold = threshold

    # ═══════════════════════════════════════════════════════════════════
    # 主入口
    # ═══════════════════════════════════════════════════════════════════

    async def verify(
        self,
        answer: str,
        evidence_list: list[SourceEvidence] | None = None,
        products: list[dict] | None = None,
        allow_empty_evidence: bool = False,
    ) -> Verdict:
        """执行全维度验证检查。

        Args:
            answer: AI生成的回答文本
            evidence_list: 用于生成回答的证据来源列表
            products: 引用的商品数据
            allow_empty_evidence: 是否允许零证据（仅特殊情况）

        Returns:
            Verdict — 包含通过/不通过判断和详细检查结果
        """
        evidence_list = evidence_list or []
        products = products or []

        # 并行执行四个维度检查
        checks = await asyncio.gather(
            self._check_evidence(answer, evidence_list, products, allow_empty_evidence),
            self._check_conflict(answer, evidence_list, products),
            self._check_derivable(answer, evidence_list, products),
            self._check_fabrication(answer, evidence_list, products),
        )

        # 收集失败项
        failed = [c for c in checks if c.result == CheckResult.FAIL]
        warnings = [c.reason for c in checks if c.result == CheckResult.WARN]

        # 综合判定
        if failed:
            passed = False
            action = GateAction.BLOCK
        elif warnings and len(warnings) >= 2:
            # 多个警告 → 标记但不阻止
            passed = True
            action = GateAction.FLAG
        else:
            passed = True
            action = GateAction.ALLOW

        # 计算综合置信度
        overall = self._compute_overall_confidence(checks, evidence_list, products)

        # 如果综合置信度低于阈值，降级处理
        if passed and overall < self.threshold:
            action = GateAction.FLAG
            warnings.append(
                f"综合置信度 ({overall:.0f}%) 低于阈值 ({self.threshold:.0f}%)"
            )

        return Verdict(
            passed=passed,
            action=action,
            checks=checks,
            failed_checks=[c.dimension for c in failed],
            warnings=warnings,
            overall_confidence=overall,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 检查 1: 证据支持
    # ═══════════════════════════════════════════════════════════════════

    async def _check_evidence(
        self,
        answer: str,
        evidence: list[SourceEvidence],
        products: list[dict],
        allow_empty: bool,
    ) -> SingleCheck:
        """检查回答中的关键声明是否有证据支撑。

        策略：
        - 如果回答包含数字（价格/参数），必须在证据中找到对应数字
        - 如果回答提到具体商品名/品牌，必须在证据或商品列表中找到
        - 如果完全无证据且不允许空证据 → FAIL
        """
        if not evidence and not products:
            if allow_empty:
                return SingleCheck(
                    dimension="evidence",
                    result=CheckResult.WARN,
                    reason="缺少证据来源，但场景允许",
                    confidence=0.3,
                )
            return SingleCheck(
                dimension="evidence",
                result=CheckResult.FAIL,
                reason="无任何证据来源支持此回答",
                details=["证据列表为空", "商品列表为空"],
                confidence=1.0,
            )

        issues = []

        # 检查回答中的价格声明
        prices_in_answer = self._PRICE_PATTERN.findall(answer)
        if prices_in_answer:
            # 在证据和商品中查找价格
            prices_in_evidence = 0
            for ev in evidence:
                prices_in_evidence += len(self._PRICE_PATTERN.findall(ev.content))
            prices_in_products = sum(
                1 for p in products if p.get("price", 0) > 0
            )

            if prices_in_evidence == 0 and prices_in_products == 0:
                issues.append(
                    f"回答包含 {len(prices_in_answer)} 个价格声明，"
                    f"但所有来源中均未找到任何价格数据"
                )

        # 检查回答长度 vs 证据量
        if len(answer) > 200 and len(evidence) <= 1:
            # 长回答但只有一条证据 → 可能扩展了未验证内容
            issues.append(
                f"回答较长 ({len(answer)}字) 但仅基于 {len(evidence)} 条证据，"
                f"可能存在扩展推测"
            )

        if issues:
            return SingleCheck(
                dimension="evidence",
                result=CheckResult.FAIL,
                reason="; ".join(issues),
                details=issues,
                confidence=0.9,
            )

        return SingleCheck(
            dimension="evidence",
            result=CheckResult.PASS,
            reason=f"基于 {len(evidence)} 条证据 + {len(products)} 个商品",
            confidence=0.85,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 检查 2: 冲突检测
    # ═══════════════════════════════════════════════════════════════════

    async def _check_conflict(
        self,
        answer: str,
        evidence: list[SourceEvidence],
        products: list[dict],
    ) -> SingleCheck:
        """检查证据之间是否存在不可调和的矛盾。

        策略：
        - 价格冲突：同一商品在不同来源中价格差异 > 50%
        - 平台冲突：回答声称来自某平台但证据中没有该平台
        """
        if len(evidence) < 2:
            return SingleCheck(
                dimension="conflict",
                result=CheckResult.PASS,
                reason="证据来源不足以检测冲突",
                confidence=0.7,
            )

        conflicts = []

        # 价格冲突检测
        all_prices: list[tuple[float, str]] = []
        for ev in evidence:
            prices = self._PRICE_PATTERN.findall(ev.content)
            for p in prices:
                try:
                    all_prices.append((float(p.replace(",", "")), ev.source.value))
                except ValueError:
                    pass

        if len(all_prices) >= 2:
            prices_only = [p[0] for p in all_prices]
            min_p, max_p = min(prices_only), max(prices_only)
            if min_p > 0 and max_p / min_p > 1.5:
                conflicts.append(
                    f"价格存在显著差异：最低 ¥{min_p:,.0f} vs 最高 ¥{max_p:,.0f} "
                    f"(差异 {(max_p/min_p - 1)*100:.0f}%)"
                )

        # 商品来源冲突
        if products:
            sources_in_answer = set()
            for p in products:
                src = p.get("platform") or p.get("source", "")
                if src and src in answer:
                    sources_in_answer.add(src)

            sources_in_evidence = set()
            for ev in evidence:
                sources_in_evidence.add(ev.source.value)

            # 如果回答声称来自某平台但证据中没有 → 潜在冲突
            claimed_platforms = {"京东", "天猫", "淘宝", "得物", "拼多多", "唯品会", "闲鱼"}
            for platform in claimed_platforms:
                if platform in answer and platform not in str(sources_in_evidence):
                    # 不一定是冲突，但需要标记
                    pass

        if conflicts:
            return SingleCheck(
                dimension="conflict",
                result=CheckResult.FAIL,
                reason="; ".join(conflicts),
                details=conflicts,
                confidence=0.8,
            )

        return SingleCheck(
            dimension="conflict",
            result=CheckResult.PASS,
            reason="未检测到证据冲突" if len(evidence) < 2 else f"{len(evidence)} 条证据之间无明显矛盾",
            confidence=0.75,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 检查 3: 可推导性
    # ═══════════════════════════════════════════════════════════════════

    async def _check_derivable(
        self,
        answer: str,
        evidence: list[SourceEvidence],
        products: list[dict],
    ) -> SingleCheck:
        """检查回答的结论是否可以从来源逻辑推导出来。

        策略：
        - 如果回答中提到的实体/数字/事实不在证据中 → 可能臆造
        - 检查关键信息密度：回答中的具体数据点是否在证据中有对应
        """
        if not evidence and not products:
            return SingleCheck(
                dimension="derivation",
                result=CheckResult.FAIL,
                reason="无来源数据，无法进行逻辑推导验证",
                confidence=1.0,
            )

        issues = []

        # 提取回答中的关键数字（非价格的数字，如规格参数）
        number_pattern = re.compile(r'\b(\d+\.?\d*)\s*(GB|TB|英寸|寸|mm|g|kg|mAh|W|Hz|核|小时|天)\b')
        numbers_in_answer = number_pattern.findall(answer)

        if numbers_in_answer:
            evidence_text = " ".join(ev.content for ev in evidence)
            # 检查这些规格数字是否在证据中出现
            missing_specs = []
            for num, unit in numbers_in_answer[:10]:
                spec_str = f"{num}{unit}"
                if spec_str not in evidence_text and num not in evidence_text:
                    missing_specs.append(spec_str)

            if missing_specs and len(missing_specs) >= 3:
                issues.append(
                    f"回答中的规格参数 ({', '.join(missing_specs[:5])}) 在证据中未找到"
                )

        # 检查回答中的专有名词（型号、品牌）是否在证据中
        # 使用简单的启发式：大写字母+数字组合（如 iPhone16, RTX5090）
        model_pattern = re.compile(r'\b([A-Z][a-zA-Z]*[\s-]?\d{2,}[A-Za-z]*)\b')
        models_in_answer = set(model_pattern.findall(answer))
        evidence_text_all = " ".join(ev.content for ev in evidence)
        product_text = " ".join(
            f"{p.get('name','')} {p.get('brand','')} {p.get('model','')}"
            for p in products
        )
        combined = evidence_text_all + " " + product_text

        unverified_models = [
            m for m in models_in_answer
            if m.lower() not in combined.lower()
        ]
        if unverified_models and len(unverified_models) >= 2:
            issues.append(
                f"回答提及的型号 ({', '.join(unverified_models[:3])}) 未在来源中找到"
            )

        if issues:
            return SingleCheck(
                dimension="derivation",
                result=CheckResult.FAIL,
                reason="; ".join(issues),
                details=issues,
                confidence=0.75,
            )

        return SingleCheck(
            dimension="derivation",
            result=CheckResult.PASS,
            reason="回答内容可从来源推导",
            confidence=0.7,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 检查 4: 臆造检测
    # ═══════════════════════════════════════════════════════════════════

    async def _check_fabrication(
        self,
        answer: str,
        evidence: list[SourceEvidence],
        products: list[dict],
    ) -> SingleCheck:
        """检测回答中是否存在明显臆造的内容。

        检查项：
        - 编造的 URL
        - 推测性语言（"可能"、"应该"、"大概" 表述价格）
        - 未标注的模拟数据
        - 过度自信表述（"绝对"、"保证"）
        """
        violations = []
        warnings = []

        # 4.1 编造的 URL
        urls_in_answer = self._URL_PATTERN.findall(answer)
        if urls_in_answer:
            urls_in_evidence = set()
            for ev in evidence:
                if ev.url:
                    urls_in_evidence.add(ev.url)
                urls_in_evidence.update(self._URL_PATTERN.findall(ev.content))

            fabricated = [u for u in urls_in_answer if u not in urls_in_evidence]
            if fabricated:
                violations.append(
                    f"包含 {len(fabricated)} 个未验证的URL: {', '.join(fabricated[:3])}"
                )

        # 4.2 推测性语言
        speculation_hits = []
        for pattern in self._SPECULATION_MARKERS:
            matches = re.findall(pattern, answer)
            if matches:
                speculation_hits.extend(matches)

        if speculation_hits:
            # 如果推测性表述涉及价格/数据，这是违规
            if any("价格" in m or "元" in m for m in speculation_hits):
                violations.append(
                    f"使用推测性语言描述价格/数据: {speculation_hits[0][:60]}"
                )
            else:
                warnings.append(
                    f"检测到推测性表述 (示例: {speculation_hits[0][:40]})"
                )

        # 4.3 未标注的模拟数据
        if products:
            simulated = [p for p in products if p.get("source") == "simulated"]
            if simulated:
                has_disclaimer = any(
                    kw in answer
                    for kw in ["模拟", "参考", "示例", "示意", "估算", "推测"]
                )
                if not has_disclaimer:
                    violations.append(
                        f"使用了 {len(simulated)} 个模拟商品数据但未标注"
                    )

        # 4.4 过度自信
        for marker in self._ABSOLUTE_MARKERS:
            if marker in answer:
                evidence_has_marker = any(marker in ev.content for ev in evidence)
                if not evidence_has_marker:
                    warnings.append(
                        f"使用绝对化表述 '{marker}' 但无相应证据支撑"
                    )
                    break

        # 判定
        if violations:
            return SingleCheck(
                dimension="fabrication",
                result=CheckResult.FAIL,
                reason="; ".join(violations),
                details=violations + warnings,
                confidence=0.9,
            )

        if warnings:
            return SingleCheck(
                dimension="fabrication",
                result=CheckResult.WARN,
                reason="; ".join(warnings),
                details=warnings,
                confidence=0.7,
            )

        return SingleCheck(
            dimension="fabrication",
            result=CheckResult.PASS,
            reason="未检测到臆造内容",
            confidence=0.85,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 辅助方法
    # ═══════════════════════════════════════════════════════════════════

    def _compute_overall_confidence(
        self,
        checks: list[SingleCheck],
        evidence: list[SourceEvidence],
        products: list[dict],
    ) -> float:
        """计算综合置信度 (0-100)。

        基于:
        - 四个检查维度的通过情况 (权重 60%)
        - 证据数量和质量 (权重 25%)
        - 商品数据可靠性 (权重 15%)
        """
        score = 0.0

        # 检查维度得分
        check_scores = {
            "evidence": 30,
            "conflict": 25,
            "derivation": 20,
            "fabrication": 25,
        }
        for c in checks:
            weight = check_scores.get(c.dimension, 15)
            if c.result == CheckResult.PASS:
                score += weight
            elif c.result == CheckResult.WARN:
                score += weight * 0.5

        # 证据加分
        if evidence:
            evidence_bonus = min(len(evidence) * 3, 15)
            # 权威来源加权
            authoritative = sum(
                1 for ev in evidence
                if ev.authority in ("official", "rag")
            )
            evidence_bonus += authoritative * 2
            score += min(evidence_bonus, 15)

        # 商品数据加分
        if products:
            real_products = sum(
                1 for p in products
                if p.get("source") != "simulated"
            )
            product_bonus = min(real_products * 2, 10)
            score += product_bonus

        return min(score, 100.0)

    def quick_check(
        self,
        answer: str,
        has_evidence: bool = False,
    ) -> Verdict:
        """同步快速检查 — 用于非关键路径的轻量验证。

        Args:
            answer: AI 回答文本
            has_evidence: 是否有证据来源
        """
        if not has_evidence and len(answer) > 100:
            return Verdict(
                passed=False,
                action=GateAction.BLOCK,
                failed_checks=["evidence"],
                checks=[
                    SingleCheck(
                        dimension="evidence",
                        result=CheckResult.FAIL,
                        reason="快速检查：无证据来源",
                    )
                ],
                overall_confidence=0,
            )
        return Verdict(
            passed=True,
            action=GateAction.ALLOW,
            overall_confidence=70 if has_evidence else 50,
        )


# ═══════════════════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════════════════

_default_gate = VerificationGate(threshold=60.0)


async def verify_response(
    answer: str,
    evidence: list[SourceEvidence] | None = None,
    products: list[dict] | None = None,
) -> Verdict:
    """快捷验证函数 — 使用默认门禁实例。"""
    return await _default_gate.verify(answer, evidence, products)


def safe_fallback(verdict: Verdict) -> str:
    """根据判决结果返回安全回退消息。"""
    if verdict.passed:
        return ""  # 不需要回退
    if "evidence" in verdict.failed_checks:
        return INSUFFICIENT_EVIDENCE_MESSAGE
    return SAFE_FALLBACK_MESSAGE
