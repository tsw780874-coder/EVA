"""Tool Registry — 工具注册表和调度器

提供：
  - 工具注册/查找
  - Function Calling schema 生成
  - 并行工具执行（含超时控制）

用法:
    from app.tools.registry import registry, tool

    @tool("product_search", category=ToolCategory.SEARCH)
    async def search_products(query: str, **kwargs) -> ToolResult:
        ...

    # 获取所有 OpenAI Function Calling schemas
    schemas = registry.get_openai_schemas()
"""

import asyncio
import time
from collections.abc import Callable, Awaitable
from app.tools.schema import ToolResult, ToolDefinition, ToolCategory, ToolStatus
from app.config import get_settings

# 工具执行函数签名
ToolFunc = Callable[..., Awaitable[ToolResult]]

# 默认超时（毫秒）
DEFAULT_TOOL_TIMEOUT = 0.8  # 800ms


class ToolRegistry:
    """工具注册表 — 管理所有可用工具"""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._funcs: dict[str, ToolFunc] = {}

    def register(
        self,
        name: str,
        description: str,
        category: ToolCategory,
        parameters: dict,
        required_role: str = "free",
    ):
        """装饰器：注册工具函数"""

        def decorator(func: ToolFunc) -> ToolFunc:
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                category=category,
                parameters=parameters,
                required_role=required_role,
            )
            self._funcs[name] = func
            return func

        return decorator

    def get(self, name: str) -> ToolDefinition | None:
        """获取工具定义"""
        return self._tools.get(name)

    def get_func(self, name: str) -> ToolFunc | None:
        """获取工具执行函数"""
        return self._funcs.get(name)

    def list_tools(self, role: str = "free") -> list[ToolDefinition]:
        """列出用户角色可用的工具"""
        if role == "admin":
            return list(self._tools.values())
        return [t for t in self._tools.values() if t.required_role == "free"]

    def get_openai_schemas(self, role: str = "free") -> list[dict]:
        """生成 OpenAI Function Calling schemas"""
        return [t.to_openai_schema() for t in self.list_tools(role)]

    def get_tool_names(self) -> list[str]:
        """获取所有已注册的工具名称"""
        return list(self._tools.keys())

    async def execute(
        self,
        name: str,
        timeout: float | None = None,
        **kwargs,
    ) -> ToolResult:
        """执行单个工具调用（含超时控制）。

        Args:
            name: 工具名称
            timeout: 超时秒数，默认从配置读取 (tool_execution_timeout_ms / 1000)
        """
        func = self._funcs.get(name)
        if not func:
            return ToolResult.failed(
                tool=name,
                error=f"未知工具: {name}。可用工具: {', '.join(self._tools.keys())}",
            )

        # 读取超时配置
        if timeout is None:
            try:
                settings = get_settings()
                timeout = settings.tool_execution_timeout_ms / 1000.0
            except Exception:
                timeout = DEFAULT_TOOL_TIMEOUT

        t0 = time.perf_counter()
        try:
            result = await asyncio.wait_for(func(**kwargs), timeout=timeout)
            result.latency_ms = (time.perf_counter() - t0) * 1000
            return result
        except asyncio.TimeoutError:
            return ToolResult.failed(
                tool=name,
                error=f"工具执行超时 ({timeout:.1f}s)",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return ToolResult.failed(
                tool=name,
                error=f"{type(e).__name__}: {str(e)[:200]}",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

    async def execute_all(
        self,
        tool_calls: list[dict],
        max_concurrency: int = 8,
        per_tool_timeout: float | None = None,
    ) -> dict[str, ToolResult]:
        """并行执行多个工具调用（含超时控制）

        Args:
            tool_calls: [{"name": "product_search", "arguments": {...}}, ...]
            max_concurrency: 最大并发数
            per_tool_timeout: 每个工具的超时秒数

        Returns:
            {tool_name: ToolResult}
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def bounded_execute(call: dict) -> tuple[str, ToolResult]:
            async with semaphore:
                name = call.get("name", call.get("function", {}).get("name", ""))
                args = call.get("arguments", call.get("function", {}).get("arguments", {}))
                if isinstance(args, str):
                    import json
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                result = await self.execute(name, timeout=per_tool_timeout, **args)
                return name, result

        tasks = [bounded_execute(c) for c in tool_calls]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: dict[str, ToolResult] = {}
        for item in results_list:
            if isinstance(item, Exception):
                continue
            name, result = item
            results[name] = result

        return results


# ═══════════════════════════════════════════════════════════════════════
# 全局注册表单例
# ═══════════════════════════════════════════════════════════════════════

registry = ToolRegistry()

# 便捷装饰器
tool = registry.register
