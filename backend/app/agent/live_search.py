"""Live Search — real-time e-commerce platform product search.

When RAG fails, this module attempts to fetch real product data from
major Chinese e-commerce platforms via HTTP scraping and search URL generation.

Strategy (in priority order):
  1. HTTP fetch product search pages with proper headers
  2. Generate clickable search URLs for users
  3. LLM-powered web search summary (when API keys available)

Usage:
    from app.agent.live_search import live_search_products

    results = await live_search_products("iPhone 16 Pro Max", top_k=5)
"""

import asyncio
import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.api.v1.admin import append_log

# ═══════════════════════════════════════════════════════════════════════
# Platform configurations
# ═══════════════════════════════════════════════════════════════════════

PLATFORM_CONFIGS = [
    {
        "name": "京东",
        "search_url": "https://search.jd.com/Search?keyword={}&enc=utf-8",
        "item_selector": ".gl-item",
        "title_selector": ".p-name em",
        "price_selector": ".p-price i",
    },
    {
        "name": "淘宝",
        "search_url": "https://s.taobao.com/search?q={}",
        "item_selector": ".item",
    },
    {
        "name": "拼多多",
        "search_url": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
    },
    {
        "name": "得物",
        "search_url": "https://www.dewu.com/search?keyword={}",
    },
    {
        "name": "天猫",
        "search_url": "https://list.tmall.com/search_product.htm?q={}",
    },
    {
        "name": "唯品会",
        "search_url": "https://www.vip.com/search?keyword={}",
    },
    {
        "name": "识货",
        "search_url": "https://www.shihuo.cn/search?keyword={}",
    },
    {
        "name": "闲鱼",
        "search_url": "https://s.2.taobao.com/list/list.htm?q={}",
    },
]

# HTTP headers to avoid bot detection
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

# Shared httpx client with timeout
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0),
            follow_redirects=True,
            headers=_BROWSER_HEADERS,
            limits=httpx.Limits(max_connections=10),
        )
    return _client


# ═══════════════════════════════════════════════════════════════════════
# HTML parsing helpers
# ═══════════════════════════════════════════════════════════════════════

def _extract_prices_from_html(html: str) -> list[dict]:
    """Extract potential product info from raw HTML using regex patterns."""
    results: list[dict] = []

    # Pattern 1: JSON-LD structured data
    json_ld_pattern = re.compile(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in json_ld_pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict) and data.get("@type") == "Product":
                results.append({
                    "name": data.get("name", ""),
                    "price": _parse_price(data.get("offers", {}).get("price", "")),
                    "url": data.get("offers", {}).get("url", ""),
                })
        except (json.JSONDecodeError, KeyError):
            pass

    # Pattern 2: ¥ price pattern with nearby title text
    price_pattern = re.compile(
        r'(?:title|alt)=["\']([^"\']{4,80})["\'].*?[¥￥]\s*([\d,]+\.?\d*)',
        re.DOTALL,
    )
    for match in price_pattern.finditer(html):
        name = match.group(1).strip()
        price = _parse_price(match.group(2))
        if name and price > 0:
            results.append({"name": name, "price": price})

    # Pattern 3: Generic price in HTML
    price_generic = re.findall(r'[¥￥]\s*([\d,]+\.?\d{0,2})', html)
    if price_generic:
        prices = [_parse_price(p) for p in price_generic[:10] if _parse_price(p) > 0]

    return results


def _parse_price(price_str: str) -> float:
    """Parse a price string to float."""
    if not price_str:
        return 0.0
    try:
        cleaned = re.sub(r'[^\d.]', '', str(price_str))
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def _extract_product_titles(html: str) -> list[str]:
    """Extract product titles from HTML meta tags and other patterns."""
    titles: list[str] = []

    # Meta og:title
    for match in re.finditer(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html):
        titles.append(match.group(1))

    # Meta description
    for match in re.finditer(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', html):
        desc = match.group(1)
        if len(desc) > 10:
            titles.append(desc[:200])

    # Title tag
    for match in re.finditer(r'<title>([^<]+)</title>', html):
        titles.append(match.group(1).strip())

    return titles


# ═══════════════════════════════════════════════════════════════════════
# Platform search
# ═══════════════════════════════════════════════════════════════════════

async def _search_platform(
    platform: dict,
    query: str,
    timeout: float = 6.0,
) -> list[dict]:
    """Search a single platform and extract product data."""
    try:
        url = platform["search_url"].format(quote(query))
        client = _get_client()

        resp = await client.get(url, timeout=timeout)
        if resp.status_code != 200:
            return []

        html = resp.text

        # Extract product info from response
        products: list[dict] = []
        extracted = _extract_prices_from_html(html)
        titles = _extract_product_titles(html)

        for item in extracted[:5]:
            products.append({
                "name": item.get("name", query),
                "price": item.get("price", 0.0),
                "platform": platform["name"],
                "url": url,
                "confidence": 40.0,  # Live scrape: lower confidence than cache/RAG
            })

        # If no structured data, at minimum create a search link entry
        if not products:
            products.append({
                "name": f"{query} — {platform['name']}搜索结果",
                "price": 0.0,
                "platform": platform["name"],
                "url": url,
                "confidence": 20.0,
            })

        return products[:3]

    except (httpx.TimeoutException, httpx.ConnectError, asyncio.TimeoutError):
        return []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════
# LLM-powered web search (uses LLM to summarize web results)
# ═══════════════════════════════════════════════════════════════════════

async def _llm_web_search(
    query: str,
    user_id: str = "",
) -> list[dict]:
    """Use LLM to search the web for product information.

    This is the fallback when direct HTTP scraping fails.
    LLM can use its training knowledge to provide real product info,
    but it's marked with appropriate confidence levels.
    """
    try:
        from app.agent.llm_utils import llm_call

        system_prompt = (
            "你是一个电商商品搜索专家。请根据用户查询，搜索你知识库中已知的真实商品信息。\n"
            "规则：\n"
            "1. 只返回你确认在真实电商平台（京东、天猫、淘宝、拼多多、得物等）上存在的商品\n"
            "2. 如果不确定价格，标注为0\n"
            "3. 返回JSON数组，每个元素包含：name(商品名), platform(平台), price(价格), url(留空)\n"
            "4. 至少返回1个结果，最多5个\n"
            "5. 不要编造商品 — 如果完全不知道，返回空数组 []\n"
            "6. JSON放在```json代码块中"
        )

        content, provider, elapsed = await llm_call(
            system_prompt=system_prompt,
            user_message=f"搜索以下商品在主流电商平台上的真实信息：{query}",
            max_tokens=600,
            temperature=0.2,
            user_id=user_id,
            node_name="live_search_llm",
        )

        if not content:
            return []

        # Extract JSON
        match = re.search(r"```json\s*([\s\S]*?)```", content)
        if not match:
            match = re.search(r"\[[\s\S]*\]", content)
        json_str = match.group(1) if match else content

        try:
            results = json.loads(json_str)
            if isinstance(results, list):
                for r in results:
                    r.setdefault("confidence", 35.0)
                    r.setdefault("source", "llm_web_search")
                    r.setdefault("platform", r.get("platform", "多个平台"))
                    r.setdefault("url", "")
                return results[:5]
        except json.JSONDecodeError:
            pass

        return []

    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════
# Search URL generation (always available)
# ═══════════════════════════════════════════════════════════════════════

def generate_search_urls(query: str) -> list[dict]:
    """Generate clickable search URLs for all major platforms.

    This is the ultimate fallback — it always works because it just
    generates URLs. Users can click to search directly on each platform.
    """
    results = []
    for p in PLATFORM_CONFIGS[:6]:  # Top 6 platforms
        results.append({
            "title": f"在{p['name']}搜索「{query}」",
            "price": "",
            "platform": p["name"],
            "url": p["search_url"].format(quote(query)),
            "confidence": 10.0,
            "source": "search_link",
        })
    return results


# ═══════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════

async def live_search_products(
    query: str,
    top_k: int = 5,
    user_id: str = "",
    timeout: float = 10.0,
) -> list[dict]:
    """Search for products across major e-commerce platforms in real-time.

    Tries in order:
      1. Parallel HTTP scrape of top platforms (京东, 淘宝, 得物)
      2. LLM-powered web search as fallback
      3. Search URL generation (always available)

    Args:
        query: Product search query
        top_k: Max results to return
        user_id: User ID for LLM quota tracking
        timeout: Total timeout for all operations

    Returns:
        List of product dicts with title/price/platform/url/confidence
    """
    t_start = time.perf_counter()
    all_results: list[dict] = []

    # Phase 1: Parallel scrape top platforms (fast platforms first)
    scrape_platforms = [p for p in PLATFORM_CONFIGS if p["name"] in ("京东", "淘宝", "得物", "拼多多")]
    try:
        tasks = [
            asyncio.wait_for(_search_platform(p, query, timeout=min(timeout / 2, 4.0)), timeout=min(timeout / 2, 4.0))
            for p in scrape_platforms
        ]
        platform_results = await asyncio.gather(*tasks, return_exceptions=True)
        for results in platform_results:
            if isinstance(results, list):
                all_results.extend(results)
    except Exception:
        pass

    elapsed = time.perf_counter() - t_start
    append_log("DEBUG", f"Live search phase 1: {len(all_results)} results in {elapsed:.1f}s")

    # Phase 2: LLM web search (if scraping yielded nothing useful)
    useful = [r for r in all_results if r.get("price", 0) > 0]
    if not useful and elapsed < timeout:
        try:
            llm_results = await asyncio.wait_for(
                _llm_web_search(query, user_id),
                timeout=timeout - elapsed,
            )
            all_results.extend(llm_results)
            append_log("INFO", f"Live search LLM fallback: {len(llm_results)} results")
        except asyncio.TimeoutError:
            pass

    # Phase 3: Always add search URLs as last resort
    if not all_results:
        all_results = generate_search_urls(query)
        append_log("INFO", f"Live search URL fallback: {len(all_results)} links generated")

    # Deduplicate by name
    seen: set[str] = set()
    final: list[dict] = []
    for r in all_results:
        name = r.get("name", r.get("title", ""))
        key = hashlib.md5(name.encode()).hexdigest()
        if key not in seen:
            seen.add(key)
            # Normalize the result format
            final.append({
                "title": r.get("name", r.get("title", query)),
                "price": r.get("price", 0.0) if r.get("price") else "",
                "platform": r.get("platform", "多个平台"),
                "url": r.get("url", ""),
                "confidence": r.get("confidence", 20.0),
                "source": r.get("source", "live_search"),
            })

    # Sort by confidence descending
    final.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    result = final[:top_k]
    total_elapsed = (time.perf_counter() - t_start) * 1000
    append_log(
        "SUCCESS" if result else "WARN",
        f"Live search complete: {len(result)} results for '{query[:40]}' ({total_elapsed:.0f}ms)",
    )

    return result


async def quick_price_check(query: str) -> dict | None:
    """Fast price check across platforms. Returns best price found."""
    results = await live_search_products(query, top_k=10, timeout=6.0)
    priced = [r for r in results if r.get("price") and float(r.get("price", 0)) > 0]
    if not priced:
        return None

    priced.sort(key=lambda x: float(x.get("price", 0)))
    best = priced[0]
    return {
        "best_price": float(best["price"]),
        "best_platform": best["platform"],
        "price_range": f"¥{float(best['price']):,.0f} - ¥{float(priced[-1]['price']):,.0f}" if len(priced) > 1 else f"¥{float(best['price']):,.0f}",
        "platforms_checked": len(results),
        "priced_results": len(priced),
        "confidence": best.get("confidence", 20),
    }


async def close_client():
    """Close the shared HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
