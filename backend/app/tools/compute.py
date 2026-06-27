"""Compute Tool — 纯计算工具（含沙箱化自定义计算）

数据源: CPU纯计算（价格分析、统计、汇率换算等）
不涉及外部数据查询，仅做数学计算。

v10: custom_calc — 子进程沙箱执行用户数学表达式
"""

import subprocess
import sys
import tempfile
import os

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry

# 沙箱配置
_SANDBOX_TIMEOUT = 3
_SANDBOX_MAX_OUTPUT = 1024


@registry.register(
    name="compute",
    description="执行纯计算任务：价格统计分析（均价/中位数/最低价）、折扣计算、预算规划。不查询外部数据，仅对输入数据进行计算。",
    category="compute",
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["price_stats", "discount", "budget", "comparison"],
                "description": "计算类型",
            },
            "prices": {
                "type": "array",
                "items": {"type": "number"},
                "description": "价格列表（price_stats/discount操作需要）",
            },
            "budget": {
                "type": "number",
                "description": "预算金额（budget操作需要）",
            },
            "original_price": {
                "type": "number",
                "description": "原价（discount操作需要）",
            },
            "current_price": {
                "type": "number",
                "description": "现价（discount操作需要）",
            },
        },
        "required": ["operation"],
    },
)
async def compute(
    operation: str,
    prices: list[float] | None = None,
    budget: float = 0,
    original_price: float = 0,
    current_price: float = 0,
) -> ToolResult:
    """纯计算工具"""
    try:
        prices = prices or []

        if operation == "price_stats" and prices:
            prices_sorted = sorted(prices)
            n = len(prices_sorted)
            mean = sum(prices_sorted) / n
            median = (
                prices_sorted[n // 2]
                if n % 2 == 1
                else (prices_sorted[n // 2 - 1] + prices_sorted[n // 2]) / 2
            )
            data = [{
                "operation": "price_stats",
                "count": n,
                "min": prices_sorted[0],
                "max": prices_sorted[-1],
                "mean": round(mean, 2),
                "median": round(median, 2),
                "range": round(prices_sorted[-1] - prices_sorted[0], 2),
            }]

        elif operation == "discount":
            if original_price > 0 and current_price > 0:
                discount_pct = round((1 - current_price / original_price) * 100, 1)
                savings = round(original_price - current_price, 2)
                data = [{
                    "operation": "discount",
                    "original_price": original_price,
                    "current_price": current_price,
                    "discount_percentage": discount_pct,
                    "savings": savings,
                    "assessment": (
                        "超值折扣" if discount_pct >= 30
                        else "不错的价格" if discount_pct >= 15
                        else "小幅优惠" if discount_pct >= 5
                        else "接近原价"
                    ),
                }]
            else:
                return ToolResult.failed(
                    tool="compute",
                    error="折扣计算需要有效的原价和现价",
                )

        elif operation == "budget" and budget > 0 and prices:
            affordable = [p for p in prices if p <= budget]
            data = [{
                "operation": "budget",
                "budget": budget,
                "total_options": len(prices),
                "affordable_count": len(affordable),
                "affordable_percentage": round(len(affordable) / len(prices) * 100, 1),
                "cheapest_option": min(prices),
                "recommended": (
                    max(affordable) if affordable else None
                ),
            }]

        elif operation == "comparison" and len(prices) >= 2:
            diff = round(abs(prices[0] - prices[1]), 2)
            data = [{
                "operation": "comparison",
                "price_a": prices[0],
                "price_b": prices[1],
                "difference": diff,
                "percentage_diff": round(diff / max(prices[0], prices[1]) * 100, 1),
                "cheaper": "A" if prices[0] < prices[1] else "B",
            }]

        elif operation == "custom_calc":
            # v10: 沙箱化自定义数学表达式 — subprocess 进程隔离
            expr = str(original_price) if original_price > 0 else ""
            if not expr or len(expr) > 200:
                return ToolResult.failed(tool="compute", error="需要有效的表达式（最长200字符）")
            # 安全过滤
            safe = set("0123456789+-*/()., math.sqrt pow abs round sum min max statistics decimal fractions")
            if any(c not in safe and not c.isalnum() and c not in ' _%' for c in expr):
                return ToolResult.failed(tool="compute", error="表达式含不安全字符")
            sandbox_code = f"""
import math, statistics, decimal, fractions
try:
    result = eval({repr(expr)}, {{"__builtins__": {{}}}}, {{"math":math,"statistics":statistics}})
    print(repr(result))
except Exception as e:
    print(f"ERROR: {{e}}")
"""
            try:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                    f.write(sandbox_code)
                    tmp_path = f.name
                try:
                    proc = subprocess.run([sys.executable, tmp_path], capture_output=True, timeout=_SANDBOX_TIMEOUT, text=True)
                    output = proc.stdout.strip()[:_SANDBOX_MAX_OUTPUT]
                    if output.startswith("ERROR:"):
                        return ToolResult.failed(tool="compute", error=output)
                    data = [{"operation": "custom_calc", "expression": expr, "result": output, "sandbox": True}]
                finally:
                    os.unlink(tmp_path)
            except subprocess.TimeoutExpired:
                return ToolResult.failed(tool="compute", error="计算超时")
            except Exception as e:
                return ToolResult.failed(tool="compute", error=f"沙箱执行失败: {e}")

        else:
            return ToolResult.failed(
                tool="compute",
                error=f"无效的计算操作: {operation}",
            )

        return ToolResult.success(
            tool="compute",
            data=data,
            confidence=0.99,  # 纯计算，置信度极高
            source="computation",
            operation=operation,
        )

    except Exception as e:
        return ToolResult.failed(
            tool="compute",
            error=f"计算失败: {str(e)[:200]}",
        )
