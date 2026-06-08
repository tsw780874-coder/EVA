"""Report generation — concise Markdown summary.

The product comparison table has been removed (products are already
displayed as interactive cards via SSE events).  The report focuses
on the purchase decision and review verdict — the only sections the
user hasn't already seen.
"""


async def report_node(state: dict) -> dict:
    search_results = state.get("search_results", [])
    price_analysis = state.get("price_analysis", {})
    review_summary = state.get("review_summary", {})
    decision = state.get("decision", {})
    user_query = state.get("user_query", "")

    lines = [
        f"## {user_query}",
        "",
    ]

    # --- Price verdict (compact) ---
    if price_analysis and search_results:
        best_p = price_analysis.get("best_platform", "?")
        best_pr = price_analysis.get("best_price", 0)
        avg = price_analysis.get("average_price", 0)
        lines.append(f"**最佳价格**：{best_p} ¥{best_pr:,.0f}（均价 ¥{avg:,.0f}）")
        lines.append("")

    # --- Review summary ---
    if review_summary:
        verdict = review_summary.get("verdict", "")
        pros = review_summary.get("pros", [])
        cons = review_summary.get("cons", [])
        if verdict:
            parts = []
            if pros:
                parts.append("优点：" + "；".join(pros))
            if cons:
                parts.append("缺点：" + "；".join(cons))
            if parts:
                lines.append(" | ".join(parts))
            lines.append(f"**口碑**：{verdict}")
            lines.append("")

    # --- Decision ---
    if decision:
        rec = decision.get("recommendation", "")
        if rec == "buy":
            lines.append(f"> ✅ 推荐购买 — {decision.get('reason', '')}")
        elif rec == "insufficient_data":
            lines.append(f"> ⚠️ 数据不足 — {decision.get('reason', '')}")
        else:
            lines.append(f"> ⚠️ 慎重考虑 — {decision.get('reason', '')}")

    lines.append("")
    lines.append("*EVA Agent 智能生成 | 数据仅供参考*")

    report = "\n".join(lines)

    return {
        "final_report": report,
        "messages": [{"role": "report_agent", "content": "购物分析报告已生成"}],
    }
