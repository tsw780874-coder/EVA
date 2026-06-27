"""Compute Tool — 纯计算工具

数据源: CPU纯计算（价格分析、统计、汇率换算等）
不涉及外部数据查询，仅做数学计算。
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


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
