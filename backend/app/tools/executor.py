"""Tool Executor — 统一工具调度器

结合 LLM Function Calling 的工具执行引擎：
  1. 接收 LLM 返回的 tool_calls
  2. 并行执行多个工具
  3. 返回统一 ToolResult
  4. 错误隔离（一个工具失败不影响其他）

用法:
    from app.tools.executor import ToolExecutor

    executor = ToolExecutor()
    results = await executor.execute_llm_tool_calls(tool_calls)
"""

import asyncio
import time
from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry

# 导入所有工具以触发注册
import app.tools.product_search    # noqa: F401
import app.tools.price_compare     # noqa: F401
import app.tools.rag_search        # noqa: F401
import app.tools.web_search        # noqa: F401
import app.tools.db_query          # noqa: F401
import app.tools.memory_query      # noqa: F401
import app.tools.review_analyze    # noqa: F401
import app.tools.compute           # noqa: F401


class ToolExecutor:
    """统一工具调度器 — 解析 LLM tool_calls 并执行"""

    def __init__(self, max_concurrency: int = 8):
        self.max_concurrency = max_concurrency

    async def execute_llm_tool_calls(
        self,
        tool_calls: list[dict],
    ) -> dict[str, ToolResult]:
        """执行 LLM 返回的 tool_calls

        Args:
            tool_calls: OpenAI 格式的 tool_calls
                [{"id": "...", "function": {"name": "...", "arguments": "..."}}, ...]

        Returns:
            {tool_call_id: ToolResult}
        """
        t0 = time.perf_counter()

        # 转换为 registry 格式
        calls = []
        for tc in tool_calls:
            func = tc.get("function", tc)
            calls.append({
                "id": tc.get("id", func.get("name", "unknown")),
                "name": func.get("name", ""),
                "arguments": func.get("arguments", {}),
            })

        # 并行执行
        results = await registry.execute_all(calls, self.max_concurrency)

        # 按 tool_call_id 重新映射
        id_results: dict[str, ToolResult] = {}
        for call in calls:
            name = call["name"]
            call_id = call["id"]
            id_results[call_id] = results.get(
                name,
                ToolResult.failed(tool=name, error="工具执行超时或未返回"),
            )

        total_ms = (time.perf_counter() - t0) * 1000
        for r in id_results.values():
            if not r.metadata:
                r.metadata = {}
            r.metadata["total_dispatch_ms"] = total_ms

        return id_results

    def format_tool_results_for_llm(
        self,
        results: dict[str, ToolResult],
    ) -> list[dict]:
        """将工具执行结果格式化为 LLM 可理解的 messages

        Args:
            results: {tool_call_id: ToolResult}

        Returns:
            OpenAI 格式的 tool result messages
        """
        messages = []
        for call_id, result in results.items():
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": result.to_dict(),
            })
        return messages

    def get_available_tools_summary(self) -> str:
        """获取可用工具摘要（用于系统提示）"""
        tools = registry.list_tools()
        lines = ["可用工具："]
        for t in tools:
            lines.append(f"  - {t.name}: {t.description[:80]}")
        return "\n".join(lines)

    @property
    def openai_tool_schemas(self) -> list[dict]:
        """获取 OpenAI Function Calling 格式的工具 schema"""
        return registry.get_openai_schemas()


# ═══════════════════════════════════════════════════════════════════════
# 单例
# ═══════════════════════════════════════════════════════════════════════

executor = ToolExecutor()
