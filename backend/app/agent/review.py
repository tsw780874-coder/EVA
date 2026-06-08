import json
import re
from app.agent.state import AgentState
from app.agent.llm_utils import llm_call


async def review_node(state: AgentState) -> dict:
    products = state.get("search_results", [])
    user_id = state.get("user_id", "")

    if not products:
        return {
            "review_summary": {"verdict": "暂无商品可分析"},
            "messages": [{"role": "review_agent", "content": "无商品数据"}],
        }

    product_text = "\n".join(
        f"- {p.get('name','')} ({p.get('platform','')}): "
        f"¥{p.get('price',0)}, 评分{p.get('rating',0)}"
        for p in products
    )

    content, provider = await llm_call(
        system_prompt=(
            "你是商品评论分析专家。根据商品信息给出pros/cons各2条和购买建议verdict。"
            '返回JSON: {"pros":[],"cons":[],"verdict":""}'
        ),
        user_message=product_text,
        max_tokens=200,
        temperature=0.5,
        user_id=user_id,
        node_name="review_node",
        stream=True,  # token streaming for instant UX feedback
    )

    if not content:
        return {
            "review_summary": {"verdict": "评论分析不可用", "pros": [], "cons": [], "error": True},
            "messages": [{"role": "review_agent", "content": "评论分析失败，所有AI模型不可用"}],
            "error": "评论分析失败",
        }

    try:
        match = re.search(r"\{[\s\S]*\}", content)
        summary = json.loads(match.group(0)) if match else {}
    except Exception:
        return {
            "review_summary": {"verdict": "评论数据解析失败", "pros": [], "cons": [], "error": True},
            "messages": [{"role": "review_agent", "content": "评论分析数据解析失败"}],
            "error": "评论JSON解析失败",
        }

    return {
        "review_summary": summary,
        "messages": [{"role": "review_agent", "content": f"评论分析: {summary.get('verdict', '')}"}],
    }
