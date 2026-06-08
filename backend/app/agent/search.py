import hashlib
import json
import re
import uuid
from functools import lru_cache
from urllib.parse import quote
from app.agent.state import AgentState
from app.agent.llm_utils import llm_call

PLATFORM_URLS = {
    "京东": "https://search.jd.com/Search?keyword={}",
    "天猫": "https://list.tmall.com/search_product.htm?q={}",
    "淘宝": "https://s.taobao.com/search?q={}",
    "得物": "https://www.dewu.com/search?keyword={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
}

PRODUCT_IMAGE_POOL = {
    "耳机": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop",
    "蓝牙": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400&h=400&fit=crop",
    "手机": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=400&h=400&fit=crop",
    "iPhone": "https://images.unsplash.com/photo-1512054502232-10a0a035e672?w=400&h=400&fit=crop",
    "笔记本": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=400&h=400&fit=crop",
    "平板": "https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=400&h=400&fit=crop",
    "相机": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=400&h=400&fit=crop",
    "手表": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400&h=400&fit=crop",
    "鞋": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400&h=400&fit=crop",
    "美妆": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=400&h=400&fit=crop",
    "护肤": "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=400&h=400&fit=crop",
    "包": "https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400&h=400&fit=crop",
    "香水": "https://images.unsplash.com/photo-1541643600914-78b084683601?w=400&h=400&fit=crop",
    "电视": "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=400&h=400&fit=crop",
    "音箱": "https://images.unsplash.com/photo-1545454675-3531b543be5d?w=400&h=400&fit=crop",
    "键盘": "https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=400&h=400&fit=crop",
    "鼠标": "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=400&h=400&fit=crop",
    "显示器": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=400&h=400&fit=crop",
    "显卡": "https://images.unsplash.com/photo-1591488320449-011701bb9704?w=400&h=400&fit=crop",
    "游戏机": "https://images.unsplash.com/photo-1486401899868-0e435ed85128?w=400&h=400&fit=crop",
    "Switch": "https://images.unsplash.com/photo-1578303512597-81e6cc155b3e?w=400&h=400&fit=crop",
    "PS5": "https://images.unsplash.com/photo-1606811841689-23dfddce3e95?w=400&h=400&fit=crop",
    "家电": "https://images.unsplash.com/photo-1585771724684-38269d6639fd?w=400&h=400&fit=crop",
    "床垫": "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=400&h=400&fit=crop",
    "家具": "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400&h=400&fit=crop",
    "灯": "https://images.unsplash.com/photo-1507473885765-e6ed057ab6fe?w=400&h=400&fit=crop",
    "default": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=400&h=400&fit=crop",
}


@lru_cache(maxsize=512)
def _pick_image(name: str) -> str:
    for keyword, url in PRODUCT_IMAGE_POOL.items():
        if keyword in name:
            return url
    seed = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"https://picsum.photos/seed/{seed}/400/400"


def _enrich_product(p: dict) -> dict:
    name = p.get("name", "未知")
    platform = p.get("platform", "未知")

    seed = f"{name}_{platform}"
    pid = str(uuid.UUID(hashlib.md5(seed.encode()).hexdigest()))

    url = p.get("url", "")
    if not url:
        url_template = PLATFORM_URLS.get(platform)
        if url_template:
            url = url_template.format(quote(name))

    image_url = p.get("image_url", "") or p.get("imageUrl", "")
    if not image_url or "example.com" in image_url or "placeholder" in image_url.lower():
        image_url = _pick_image(name)

    p["id"] = pid
    p["url"] = url
    p["image_url"] = image_url

    for field in ("price", "original_price", "rating"):
        if field in p and p[field] is not None:
            try:
                p[field] = float(p[field])
            except (ValueError, TypeError):
                pass
    return p


async def search_node(state: AgentState) -> dict:
    query = state.get("user_query", "")
    intent = state.get("intent", "")
    user_id = state.get("user_id", "")

    # Use streaming LLM call for faster first-token
    content, provider = await llm_call(
        system_prompt=(
            "你是电商搜索专家。根据用户查询生成3个不同平台的模拟商品。"
            "返回JSON数组，每项: name/platform/price/original_price/rating/review_count。"
            "价格人民币，JSON放在```json代码块中。"
        ),
        user_message=f"查询:{query}",
        max_tokens=400,
        temperature=0.3,
        user_id=user_id,
        node_name="search_node",
        stream=True,  # token streaming for instant UX feedback
        bypass_cache=False,
    )

    if not content:
        return {
            "search_results": [],
            "search_attempted": True,
            "messages": [{"role": "search_agent", "content": "商品搜索失败，所有AI模型不可用"}],
            "error": "搜索失败: 所有模型不可用",
        }

    try:
        match = re.search(r"```json\s*([\s\S]*?)```", content)
        if match:
            results = json.loads(match.group(1))
        else:
            results = json.loads(content)
    except Exception:
        return {
            "search_results": [],
            "search_attempted": True,
            "messages": [{"role": "search_agent", "content": "商品搜索结果解析失败"}],
            "error": "搜索JSON解析失败",
        }

    enriched = [_enrich_product(p) for p in results]

    return {
        "search_results": enriched,
        "search_attempted": True,
        "messages": [{"role": "search_agent", "content": f"找到 {len(enriched)} 个商品"}],
    }
