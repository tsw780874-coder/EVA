async def price_node(state: dict) -> dict:
    search_results = state.get("search_results", [])
    if not search_results:
        return {"price_analysis": {}, "messages": [{"role": "price_agent", "content": "未找到商品可进行价格对比"}]}

    prices = [(p["platform"], p["price"], p.get("original_price", p["price"])) for p in search_results]
    sorted_prices = sorted(prices, key=lambda x: x[1])
    best_platform = sorted_prices[0]

    analysis = {
        "best_price": best_platform[1],
        "best_platform": best_platform[0],
        "average_price": round(sum(p[1] for p in prices) / len(prices), 2),
        "price_range": f"¥{sorted_prices[0][1]} - ¥{sorted_prices[-1][1]}",
        "max_discount": max(
            ((orig - price) / orig * 100 for _, price, orig in prices if orig > price),
            default=0,
        ),
        "platforms": [{"name": p[0], "price": p[1], "original": p[2]} for p in prices],
    }

    return {
        "price_analysis": analysis,
        "messages": [{"role": "price_agent", "content": f"价格分析完成：最低价 ¥{best_platform[1]} ({best_platform[0]})"}],
    }
