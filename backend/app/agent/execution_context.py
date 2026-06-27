"""EVA Request Isolation Layer v6.0 — 每次请求 = 完全独立执行单元

核心原则：
  1. 每个请求生成唯一 execution_id（UUID）
  2. 搜索使用纯净 user_query（不含历史）
  3. LLM 上下文与搜索 query 完全隔离
  4. 缓存按 execution_id 隔离（请求结束立即销毁）
  5. 结果验证：输出 query 必须匹配输入 query

禁止行为：
  ❌ 跨请求共享搜索结果
  ❌ 全局缓存泄漏
  ❌ 历史对话污染搜索
  ❌ previous_query 引用

用法:
    from app.agent.execution_context import ExecutionContext, IsolationGuard

    ctx = ExecutionContext(user_query="我要买篮球鞋", session_id="s1")
    # 搜索只用 ctx.user_query
    # LLM 可用 ctx.chat_summary（短摘要，非完整历史）
"""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """每次请求的独立执行上下文 — 不可跨请求共享。"""
    execution_id: str           # 唯一请求ID
    user_query: str             # 纯净用户输入（搜索用）
    session_id: str             # 会话ID（仅用于日志追踪，不用于搜索）
    timestamp: float            # 请求时间戳
    chat_summary: str           # 历史对话摘要（仅LLM用，最多3条）
    category_constraint: object | None = None  # 类目约束
    intent: str = ""            # 意图分类结果

    # 请求级缓存（请求结束销毁）
    _request_cache: dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return bool(self.user_query) and len(self.user_query.strip()) >= 1

    def cache_get(self, key: str) -> object | None:
        return self._request_cache.get(key)

    def cache_set(self, key: str, value: object) -> None:
        self._request_cache[key] = value

    def destroy(self) -> None:
        """请求结束：销毁所有缓存。"""
        self._request_cache.clear()


class IsolationGuard:
    """查询隔离守卫 — 检测和阻止状态泄漏。"""

    @staticmethod
    def guard_query_match(expected: str, actual: str) -> bool:
        """验证查询是否匹配 — 防止串线。"""
        return expected.strip().lower() == actual.strip().lower()

    @staticmethod
    def guard_category_match(
        product_category: str, expected_primary: str
    ) -> bool:
        """验证商品类目是否匹配 — 防止跨类目污染。"""
        if not expected_primary:
            return True
        return expected_primary.lower() in (product_category or "").lower()

    @staticmethod
    def guard_no_history_leak(
        response_text: str, history_queries: list[str]
    ) -> bool:
        """检测响应中是否泄漏了历史查询。"""
        for old_q in history_queries:
            if old_q.strip().lower() in response_text.lower():
                return False
        return True


def create_execution_context(
    user_query: str,
    session_id: str = "",
    chat_history: list[dict] | None = None,
) -> ExecutionContext:
    """创建独立执行上下文 — 每次请求调用一次。

    Args:
        user_query: 用户当前输入（纯净，不拼接历史）
        session_id: 会话ID（仅用于追踪）
        chat_history: 历史对话（仅提取摘要给LLM，不用于搜索）

    Returns:
        ExecutionContext — 独立的请求上下文
    """
    # 提取 LLM 摘要（最多3条最近消息，不污染搜索）
    chat_summary = ""
    if chat_history:
        recent = chat_history[-3:]  # 仅最近3条
        lines = []
        for m in recent:
            role = "用户" if m.get("role") == "user" else "助手"
            content = (m.get("content") or "")[:80]
            if content.strip():
                lines.append(f"{role}: {content}")
        chat_summary = "\n".join(lines)

    return ExecutionContext(
        execution_id=str(uuid.uuid4())[:12],
        user_query=user_query.strip(),
        session_id=session_id,
        timestamp=time.time(),
        chat_summary=chat_summary,
    )
