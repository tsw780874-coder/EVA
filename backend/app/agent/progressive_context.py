"""Progressive Context Builder — 逐步构建LLM上下文，搜索结果到达即注入。

核心设计：
  - LLM 流式输出不等待搜索完成
  - 搜索结果通过 context_version 机制逐步注入
  - 每个新结果到达时触发一次上下文更新
  - 支持多源数据并行到达时的合并

用法:
    builder = ProgressiveContextBuilder(user_query, intent)
    await builder.add_products(products, "hot_products")
    await builder.add_rag_docs(rag_docs)
    prompt = builder.build_prompt()
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal

from app.api.v1.admin import append_log


@dataclass
class ContextSnapshot:
    """上下文快照 — 用于渐进式增强LLM输出"""
    products: list[dict] = field(default_factory=list)
    rag_docs: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    version: int = 0
    timestamp: float = 0.0


class ProgressiveContextBuilder:
    """渐进式上下文构建器。

    解决核心问题：LLM 不应该等待所有搜索完成再开始输出。
    搜索结果陆续到达时，动态构建 prompt 注入 LLM。
    """

    def __init__(self, user_query: str, intent: str = "shopping"):
        self.user_query = user_query
        self.intent = intent
        self._lock = asyncio.Lock()
        self._snapshot = ContextSnapshot(timestamp=time.time())
        self._on_context_update: list[asyncio.Event] = []

    # ── 数据注入接口 ──

    async def add_products(self, products: list[dict], source: str) -> int:
        """添加商品数据，返回新的 context_version"""
        async with self._lock:
            existing_names = {p.get("name", "") for p in self._snapshot.products}
            for p in products:
                if p.get("name", "") not in existing_names:
                    self._snapshot.products.append(p)
                    existing_names.add(p.get("name", ""))
            if source not in self._snapshot.sources:
                self._snapshot.sources.append(source)
            self._snapshot.version += 1
            self._snapshot.timestamp = time.time()
            self._notify_updates()
            return self._snapshot.version

    async def add_rag_docs(self, docs: list[dict]) -> int:
        """添加RAG文档"""
        async with self._lock:
            for doc in docs:
                if doc not in self._snapshot.rag_docs:
                    self._snapshot.rag_docs.append(doc)
            self._snapshot.version += 1
            self._snapshot.timestamp = time.time()
            self._notify_updates()
            return self._snapshot.version

    async def add_tool_results(self, results: list[dict]) -> int:
        """添加工具调用结果"""
        async with self._lock:
            self._snapshot.tool_results.extend(results)
            self._snapshot.version += 1
            self._snapshot.timestamp = time.time()
            self._notify_updates()
            return self._snapshot.version

    # ── Prompt 构建 ──

    def build_prompt(self) -> tuple[str, str]:
        """构建当前可用的最佳 prompt。

        Returns:
            (system_prompt, user_message) — 可直接传给 llm_call。
        """
        async def _inner():
            async with self._lock:
                return self._build_sync()
        # 同步版本（无需 await）
        return self._build_sync()

    def _build_sync(self) -> tuple[str, str]:
        """同步构建 prompt — 调用者必须持有锁或确认单线程"""
        products = self._snapshot.products
        rag_docs = self._snapshot.rag_docs
        tool_results = self._snapshot.tool_results
        sources = self._snapshot.sources

        # 基础系统prompt
        system_prompt = (
            "你是EVA AI购物助手。请基于提供的搜索数据回答用户问题。\n"
            "规则：\n"
            "1. 只使用下方提供的信息，不要凭记忆编造数据\n"
            "2. 如实呈现商品信息，标注数据来源\n"
            "3. 如数据不足，诚实告知而非编造\n"
            "4. 用中文回复，结构清晰\n"
        )

        # 构建上下文
        context_parts = [f"用户查询: {self.user_query}"]

        if products:
            product_lines = []
            for i, p in enumerate(products[:8], 1):
                name = p.get("name", "未知")
                platform = p.get("platform", "未知")
                price = p.get("price", 0)
                source = p.get("source", "unknown")
                conf = p.get("confidence", 0)
                product_lines.append(
                    f"[商品{i}] {name} | {platform} | ¥{price} | "
                    f"来源:{source} | 置信度:{conf:.0f}%"
                )
            context_parts.append("已找到商品:\n" + "\n".join(product_lines))

        if rag_docs:
            doc_lines = []
            for i, doc in enumerate(rag_docs[:5], 1):
                content = doc.get("content", "")[:300]
                source = doc.get("source", "知识库")
                doc_lines.append(f"[文档{i} 来源:{source}]\n{content}")
            context_parts.append("知识库检索:\n" + "\n".join(doc_lines))

        if tool_results:
            tool_lines = []
            for i, tr in enumerate(tool_results[:3], 1):
                content = str(tr.get("content", tr))[:300]
                tool_lines.append(f"[工具结果{i}]\n{content}")
            context_parts.append("工具查询:\n" + "\n".join(tool_lines))

        if not products and not rag_docs and not tool_results:
            context_parts.append(
                "注意：当前搜索仍在进行中，暂未获取到商品数据。"
                "请告知用户正在搜索中，并给出通用购物建议。"
            )

        context_parts.append(f"数据来源: {', '.join(sources) if sources else '搜索中...'}")

        user_message = "\n\n".join(context_parts)
        return system_prompt, user_message

    # ── 状态查询 ──

    @property
    def has_data(self) -> bool:
        return bool(self._snapshot.products or self._snapshot.rag_docs)

    @property
    def version(self) -> int:
        return self._snapshot.version

    @property
    def product_count(self) -> int:
        return len(self._snapshot.products)

    def get_snapshot(self) -> ContextSnapshot:
        """获取当前上下文快照"""
        return self._snapshot

    # ── 内部方法 ──

    def _notify_updates(self):
        """通知等待上下文更新的监听者"""
        for event in self._on_context_update:
            if not event.is_set():
                event.set()

    async def wait_for_update(self, timeout: float = 1.0) -> bool:
        """等待上下文更新（有新数据到达）。"""
        event = asyncio.Event()
        self._on_context_update.append(event)
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            if event in self._on_context_update:
                self._on_context_update.remove(event)


# ── 预搜索 Prompt（搜索进行中使用的占位prompt）──

_PRE_SEARCH_SYSTEM = (
    "你是EVA AI购物助手。你正在为用户搜索商品信息，请先给出简短回应。\n"
    "规则：\n"
    "1. 告知用户正在为其搜索\n"
    "2. 根据查询类型给出通用购物建议或引导\n"
    "3. 不要编造具体的价格或商品数据\n"
    "4. 用中文回复，1-2句话即可"
)


def get_pre_search_prompt(user_query: str, intent: str) -> tuple[str, str]:
    """获取搜索进行中的占位prompt"""
    return _PRE_SEARCH_SYSTEM, (
        f"用户查询: {user_query}\n"
        f"意图: {intent}\n\n"
        f"请给出简短的前置回应。"
    )
