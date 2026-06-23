"""Tool System — 统一结构化 Schema 定义

所有工具调用必须返回 ToolResult，确保输出可控、可追溯、可验证。

设计原则：
  - 每个 Tool 返回统一的 JSON Schema
  - status 必须在 {success, partial, failed} 中
  - data 必须是结构化 list[dict]
  - confidence 必须是 0.0-1.0
  - source 必须标注数据来源
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Any


class ToolStatus(str, Enum):
    SUCCESS = "success"    # 工具调用成功，返回有效数据
    PARTIAL = "partial"    # 部分成功，部分数据不可用
    FAILED = "failed"      # 调用失败


class ToolCategory(str, Enum):
    DATA = "data"          # 数据查询类（DB, API）
    SEARCH = "search"      # 搜索类（ES, Vector, BM25）
    EXTERNAL = "external"  # 外部 API（电商平台）
    COMPUTE = "compute"    # 计算类（价格分析、统计）
    MEMORY = "memory"      # 记忆类（查询历史）


@dataclass
class ToolResult:
    """统一工具返回格式 — 所有工具必须返回此结构"""
    tool: str                              # 工具名称
    status: ToolStatus                     # 调用状态
    data: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0                # 0.0 - 1.0
    source: str = ""                       # 数据来源标识
    latency_ms: float = 0.0                # 执行耗时
    error: str | None = None               # 错误信息（仅 status=failed 时）
    metadata: dict[str, Any] = field(default_factory=dict)  # 额外元数据

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "status": self.status.value,
            "data": self.data,
            "confidence": self.confidence,
            "source": self.source,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def success(cls, tool: str, data: list[dict], confidence: float,
                source: str, latency_ms: float = 0, **metadata) -> "ToolResult":
        return cls(
            tool=tool, status=ToolStatus.SUCCESS,
            data=data, confidence=confidence,
            source=source, latency_ms=latency_ms, metadata=metadata,
        )

    @classmethod
    def partial(cls, tool: str, data: list[dict], confidence: float,
                source: str, error: str = "", **metadata) -> "ToolResult":
        return cls(
            tool=tool, status=ToolStatus.PARTIAL,
            data=data, confidence=confidence,
            source=source, error=error, metadata=metadata,
        )

    @classmethod
    def failed(cls, tool: str, error: str, source: str = "",
               **metadata) -> "ToolResult":
        return cls(
            tool=tool, status=ToolStatus.FAILED,
            confidence=0.0, source=source, error=error, metadata=metadata,
        )


@dataclass
class ToolDefinition:
    """工具定义 — 用于 Function Calling 注册"""
    name: str
    description: str
    category: ToolCategory
    parameters: dict  # JSON Schema for OpenAI function calling
    required_role: str = "free"  # "admin" | "free"

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
