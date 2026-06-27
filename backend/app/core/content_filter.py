"""Content Safety Filter — input sanitization + prompt injection detection.

集成到 FastAPI 依赖链中，在 chat endpoint 进入 agent pipeline 之前拦截。

Usage:
    from app.core.content_filter import filter_content, ContentFilterResult

    result = filter_content(user_input)
    if not result.passed:
        raise HTTPException(400, detail=result.reason)
"""

import re
import unicodedata
from dataclasses import dataclass, field
from app.config import get_settings


# ═══════════════════════════════════════════════════════════════════════
# Injection patterns — 检测常见 prompt injection / jailbreak 尝试
# ═══════════════════════════════════════════════════════════════════════

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # 英文 jailbreak 关键词
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|messages?)", "prompt_injection"),
    (r"(you\s+are|act\s+as|pretend\s+to\s+be)\s+(now\s+)?(DAN|jailbreak|unfiltered|uncensored)", "jailbreak_attempt"),
    (r"system\s*prompt\s*(:|=|is|was)", "system_prompt_probe"),
    (r"(forget|override|bypass|disable)\s+(your\s+)?(rules?|constraints?|filters?|safety)", "rule_bypass"),
    (r"(developer\s*mode|debug\s*mode|admin\s*mode|god\s*mode)", "mode_switch"),
    # 中文 jailbreak
    (r"忽略(所有|之前|上述|上面)(的)?(指令|提示|规则|限制)", "prompt_injection_cn"),
    (r"(忘记|绕过|跳过|无视)(你|系统)(的)?(规则|限制|安全|过滤)", "rule_bypass_cn"),
    (r"(现在|请)(扮演|假装|伪装)(成|为)", "roleplay_bypass"),
    # Base64 编码 payload
    (r"[A-Za-z0-9+/]{80,}={0,2}", "suspicious_base64"),
    # 重复注入（超长重复字符）
    (r"(.)\1{500,}", "excessive_repetition"),
]

@dataclass
class ContentFilterResult:
    """Result of content safety check."""
    passed: bool
    reason: str = ""
    sanitized_text: str = ""
    flags: list[str] = field(default_factory=list)


def _sanitize_input(text: str) -> tuple[str, list[str]]:
    """Sanitize user input: strip null bytes, control chars, normalize Unicode.

    Returns (sanitized_text, flags).
    """
    flags: list[str] = []

    # Strip null bytes (common injection vector)
    if "\x00" in text:
        text = text.replace("\x00", "")
        flags.append("null_bytes_stripped")

    # Strip non-printable control characters (except common whitespace)
    cleaned = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 and cp not in (0x09, 0x0A, 0x0D):  # tab, LF, CR
            flags.append("control_chars_stripped")
            continue
        if cp == 0x7F:  # DEL
            flags.append("control_chars_stripped")
            continue
        cleaned.append(ch)
    text = "".join(cleaned)

    # Unicode normalization (NFC — composed form)
    normalized = unicodedata.normalize("NFC", text)
    if normalized != text:
        flags.append("unicode_normalized")
        text = normalized

    # Strip leading/trailing whitespace
    text = text.strip()

    return text, flags


def filter_content(text: str, max_length: int | None = None) -> ContentFilterResult:
    """Run all content safety checks on user input.

    Args:
        text: Raw user input text
        max_length: Max allowed length in characters (default from config or 4000)

    Returns:
        ContentFilterResult with pass/fail + reason
    """
    if max_length is None:
        try:
            settings = get_settings()
            # Cap input at reasonable size (configurable)
            max_length = 4000
        except Exception:
            max_length = 4000

    flags: list[str] = []

    # ── Check 0: Empty input ──
    if not text or not text.strip():
        return ContentFilterResult(passed=False, reason="输入内容为空", flags=["empty"])

    # ── Check 1: Length limit ──
    if len(text) > max_length:
        return ContentFilterResult(
            passed=False,
            reason=f"输入内容过长（最多{max_length}字符，当前{len(text)}字符）",
            flags=["too_long"],
        )

    # ── Check 2: Input sanitization ──
    text, sanitize_flags = _sanitize_input(text)
    flags.extend(sanitize_flags)

    if not text:
        return ContentFilterResult(passed=False, reason="输入内容无效（仅含控制字符）", flags=flags)

    # ── Check 3: Prompt injection detection ──
    text_lower = text.lower()
    for pattern, flag in _INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return ContentFilterResult(
                passed=False,
                reason=f"输入包含不安全内容，已被拦截",
                sanitized_text=text,
                flags=flags + [flag],
            )

    # ── All checks passed ──
    return ContentFilterResult(passed=True, sanitized_text=text, flags=flags)


# ═══════════════════════════════════════════════════════════════════════
# FastAPI dependency
# ═══════════════════════════════════════════════════════════════════════


class ContentFilterGuard:
    """FastAPI dependency: validates and sanitizes user input before processing."""

    def __init__(self, max_length: int | None = None):
        self.max_length = max_length or 4000

    async def __call__(self, content: str) -> str:
        """Validate and return sanitized content.

        Raises:
            ValueError: If content fails safety checks
        """
        result = filter_content(content, self.max_length)
        if not result.passed:
            raise ValueError(result.reason)
        return result.sanitized_text or content


# Singleton
content_guard = ContentFilterGuard()
