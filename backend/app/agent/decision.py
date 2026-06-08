async def decision_node(state: dict) -> dict:
    price_analysis = state.get("price_analysis", {})
    review_summary = state.get("review_summary", {})

    # 上游节点失败 → 决策数据不足
    if not price_analysis or review_summary.get("error"):
        return {
            "decision": {
                "recommendation": "insufficient_data",
                "best_platform": "数据不足",
                "best_price": 0,
                "rating": 0,
                "confidence": 0,
                "reason": "商品搜索或评论分析未能获取到真实数据，无法做出购买决策。请稍后重试。",
            },
            "messages": [{"role": "decision_agent", "content": "数据不足，无法生成购买决策"}],
        }

    best_price = price_analysis.get("best_price", 0)
    best_platform = price_analysis.get("best_platform", "未知")
    verdict = review_summary.get("verdict", "")
    pros = review_summary.get("pros", [])
    cons = review_summary.get("cons", [])

    rating = min(3 + len(pros) * 0.5, 5.0)
    rating = max(rating - len(cons) * 0.3, 1.0)

    should_buy = rating >= 4.0 and best_price > 0
    reason = (
        f"该商品在{best_platform}以¥{best_price}的价格销售，综合评分{rating:.1f}/5，{verdict}。建议购买。"
        if should_buy
        else f"该商品评价一般（{rating:.1f}/5），建议慎重考虑或寻找替代品。"
    )

    decision = {
        "recommendation": "buy" if should_buy else "consider",
        "best_platform": best_platform,
        "best_price": best_price,
        "rating": round(rating, 1),
        "confidence": round(min(rating / 5, 1.0), 2),
        "reason": reason,
    }

    return {
        "decision": decision,
        "messages": [{"role": "decision_agent", "content": f"购买决策：{reason}"}],
    }
