"""EVA Tool System — 结构化工具调用框架

提供：
  - 8 个核心工具（product_search, price_compare, rag_search, web_search,
                 db_query, memory_query, review_analyze, compute）
  - 统一 ToolResult Schema
  - 工具注册表和调度器
  - LLM Function Calling 集成

用法:
    from app.tools.executor import executor

    # 获取可用工具 schema（传给 LLM）
    schemas = executor.openai_tool_schemas

    # 执行 LLM 返回的 tool_calls
    results = await executor.execute_llm_tool_calls(tool_calls)
"""

from app.tools.schema import ToolResult, ToolStatus, ToolDefinition, ToolCategory
from app.tools.registry import registry
from app.tools.executor import executor

__all__ = [
    "ToolResult", "ToolStatus", "ToolDefinition", "ToolCategory",
    "registry", "executor",
]
