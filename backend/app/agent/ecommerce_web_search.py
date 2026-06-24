"""E-Commerce Web Search — real product links via search engines.

Finds REAL product listings on JD, PDD, Taobao, Dewu, Shihuo, Vipshop, Tmall, Xianyu
by querying Google (SerpAPI) or DuckDuckGo with platform-specific search operators.

Design:
  1. Build optimized search queries for each platform (site: operator)
  2. Query SerpAPI (primary, high quality) or DuckDuckGo (fallback, free)
  3. Parse search results to extract platform-specific product URLs + prices
  4. Apply confidence scoring based on domain tier
  5. Cache aggressively (5-min in-memory + Redis where available)

Usage:
    from app.agent.ecommerce_web_search import ecommerce_web_search

    results = await ecommerce_web_search("iPhone 16 Pro Max", top_k=5)
    # → [{title, price, platform, url, confidence, source: "ecommerce_web"}, ...]
"""

import asyncio
import hashlib
import html as html_mod
import json
import re
import time
from typing import Optional
from urllib.parse import quote

import httpx

from app.api.v1.admin import append_log
from app.config import get_settings

settings = get_settings()

# ═══════════════════════════════════════════════════════════════════════
# Platform configurations
# ═══════════════════════════════════════════════════════════════════════

# Domain regex patterns for extracting real product page links from search results
PLATFORM_LINK_PATTERNS: dict[str, re.Pattern] = {
    "京东":   re.compile(r'https?://(?:item\.jd|search\.jd)\.com/[^\s"\'<>]+'),
    "天猫":   re.compile(r'https?://(?:detail\.tmall|list\.tmall)\.com/[^\s"\'<>]+'),
    "淘宝":   re.compile(r'https?://(?:item\.taobao|s\.taobao)\.com/[^\s"\'<>]+'),
    "得物":   re.compile(r'https?://(?:www\.)?dewu\.com/[^\s"\'<>]+'),
    "拼多多": re.compile(r'https?://(?:mobile\.)?yangkeduo\.com/[^\s"\'<>]+'),
    "唯品会": re.compile(r'https?://(?:www\.)?vip\.com/[^\s"\'<>]+'),
    "识货":   re.compile(r'https?://(?:www\.)?shihuo\.cn/[^\s"\'<>]+'),
    "闲鱼":   re.compile(r'https?://(?:s\.2\.taobao|goofish)\.com/[^\s"\'<>]+'),
}

# Search query templates — platform-specific with site: operator
# These produce targeted e-commerce searches via Google/DuckDuckGo
PLATFORM_SEARCH_QUERIES: dict[str, str] = {
    "京东":   'site:jd.com "{product}" 价格',
    "天猫":   'site:tmall.com "{product}" 价格',
    "淘宝":   'site:taobao.com "{product}" 价格',
    "得物":   'site:dewu.com "{product}"',
    "拼多多": 'site:yangkeduo.com "{product}" 价格',
    "唯品会": 'site:vip.com "{product}"',
    "识货":   'site:shihuo.cn "{product}"',
    "闲鱼":   'site:goofish.com "{product}"',
}

# Direct search URL templates (for URL-generation fallback)
PLATFORM_SEARCH_URLS: dict[str, str] = {
    "京东":   "https://search.jd.com/Search?keyword={}",
    "天猫":   "https://list.tmall.com/search_product.htm?q={}",
    "淘宝":   "https://s.taobao.com/search?q={}",
    "得物":   "https://www.dewu.com/search?keyword={}",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={}",
    "唯品会": "https://www.vip.com/search?keyword={}",
    "识货":   "https://www.shihuo.cn/search?keyword={}",
    "闲鱼":   "https://s.2.taobao.com/list/list.htm?q={}",
}

# Price extraction pattern (Chinese Yuan sign)
# Price extraction patterns (aggressive — catches more real prices)
_PRICE_PATTERN = re.compile(r'[¥￥]\s*([\d,]+\.?\d{0,2})')
# Bare number price patterns: "价格: 8999", "售价 7999元", "到手价 6999"
_PRICE_KW_PATTERN = re.compile(
    r'(?:价格|售价|现价|到手价|参考价|京东价|天猫价|促销价|秒杀价|活动价|原价|券后价)'
    r'[：:\s]*[¥￥]?\s*([\d,]+\.?\d{0,2})'
)
# "8999元" or "7,999元" pattern (no ¥ prefix, just 元 suffix)
_PRICE_YUAN_PATTERN = re.compile(r'(?<!\d)([\d,]{3,7})\s*元')
# USD pattern for electronics: "$999" or "USD 999"
_PRICE_USD_PATTERN = re.compile(r'\$\s*([\d,]+\.?\d{0,2})')

# ═══════════════════════════════════════════════════════════════════════
# Google Shopping Backend (dedicated price data via SerpAPI)
# ═══════════════════════════════════════════════════════════════════════

async def _serpapi_shopping_search(query: str, top_k: int = 6, timeout: float = 3.0) -> list[dict]:
    """Search via SerpAPI Google Shopping — returns products WITH real prices."""
    api_key = settings.serpapi_key
    if not api_key:
        return []

    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google_shopping",
        "gl": "cn",
        "hl": "zh-cn",
        "num": str(top_k),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=_BROWSER_HEADERS) as client:
            resp = await client.get(SERPAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []
        for sr in data.get("shopping_results", [])[:top_k]:
            price_str = sr.get("price", "") or sr.get("extracted_price", "")
            price = _parse_price_value(price_str)

            results.append({
                "title": sr.get("title", query),
                "snippet": f"{sr.get('source', '')} | {price_str}",
                "url": sr.get("link", "") or sr.get("product_link", ""),
                "source": "serpapi_shopping",
                "price": price,
                "thumbnail": sr.get("thumbnail", ""),
                "rating": float(sr.get("rating", 0)) if sr.get("rating") else 0,
                "reviews": int(sr.get("reviews", 0)) if sr.get("reviews") else 0,
            })

        return results

    except Exception as e:
        append_log("DEBUG", f"SerpAPI Shopping failed: {str(e)[:60]}")
        return []


def _parse_price_value(price_str: str) -> float:
    """Parse a price string like '¥8,999.00' or '$999.99' or '8999元' into float."""
    if not price_str:
        return 0.0
    # Strip currency symbols
    cleaned = price_str.replace("¥", "").replace("￥", "").replace("$", "").replace("元", "")
    cleaned = cleaned.replace(",", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _extract_price(text: str) -> float:
    """Extract a price from text using multiple pattern strategies.

    Strategy order (first match wins):
      1. ¥/￥ prefix — most reliable for Chinese e-commerce
      2. Price keywords (价格/售价/etc.) — very common in CN search snippets
      3. 元 suffix with bare number — "8999元"
      4. $ prefix — for international products
    """
    if not text:
        return 0.0

    # 1. ¥/￥ prefix
    match = _PRICE_PATTERN.search(text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except (ValueError, TypeError):
            pass

    # 2. Price keyword patterns
    match = _PRICE_KW_PATTERN.search(text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except (ValueError, TypeError):
            pass

    # 3. 元 suffix (bare number, no ¥ prefix)
    match = _PRICE_YUAN_PATTERN.search(text)
    if match:
        try:
            val = float(match.group(1).replace(",", ""))
            # Sanity check: price should be reasonable (50-500,000 range for most products)
            if 50 <= val <= 500_000:
                return val
        except (ValueError, TypeError):
            pass

    # 4. $ prefix (USD)
    match = _PRICE_USD_PATTERN.search(text)
    if match:
        try:
            usd = float(match.group(1).replace(",", ""))
            # Convert USD to CNY (approximate: 1 USD ≈ 7.2 CNY)
            return round(usd * 7.2, 2)
        except (ValueError, TypeError):
            pass

    return 0.0


# ═══════════════════════════════════════════════════════════════════════
# SerpAPI Backend (Google search with Chinese locale)
# ═══════════════════════════════════════════════════════════════════════

SERPAPI_URL = "https://serpapi.com/search"


async def _serpapi_search(query: str, top_k: int = 5, timeout: float = 5.0) -> list[dict]:
    """Search via SerpAPI (Google) for e-commerce product listings."""
    api_key = settings.serpapi_key
    if not api_key:
        return []

    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": str(top_k),
        "gl": "cn",         # Chinese locale
        "hl": "zh-cn",      # Chinese language
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=_BROWSER_HEADERS) as client:
            resp = await client.get(SERPAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []
        for r in data.get("organic_results", [])[:top_k]:
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("snippet", ""),
                "url": r.get("link", ""),
                "source": "serpapi",
                "thumbnail": r.get("thumbnail", ""),
            })

        # Knowledge graph (product info cards)
        kg = data.get("knowledge_graph", {})
        if kg and kg.get("title"):
            results.insert(0, {
                "title": kg.get("title", query),
                "snippet": kg.get("description", ""),
                "url": kg.get("website", "") or kg.get("link", ""),
                "source": "serpapi_kg",
                "thumbnail": kg.get("image", ""),
            })

        # Shopping results (if available)
        for sr in data.get("shopping_results", [])[:3]:
            results.append({
                "title": sr.get("title", ""),
                "snippet": f"价格: {sr.get('price', '')} | {sr.get('source', '')}",
                "url": sr.get("link", ""),
                "source": "serpapi_shopping",
                "thumbnail": sr.get("thumbnail", ""),
            })

        return results

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        append_log("WARN", f"SerpAPI search timeout/connect: {str(e)[:80]}")
        return []
    except Exception as e:
        append_log("WARN", f"SerpAPI search failed: {str(e)[:80]}")
        return []


# ═══════════════════════════════════════════════════════════════════════
# Bing Web Search API Backend (free tier: 1000/mo, works in China)
# ═══════════════════════════════════════════════════════════════════════

BING_API_URL = "https://api.bing.microsoft.com/v7.0/search"


async def _bing_search(query: str, top_k: int = 5, timeout: float = 5.0) -> list[dict]:
    """Search via Bing Web Search API for e-commerce product listings.

    Bing API has a free tier (1000 transactions/month) and works well
    in China with the zh-CN market setting.
    """
    api_key = settings.bing_api_key
    if not api_key:
        return []

    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Accept-Language": "zh-CN",
    }

    params = {
        "q": query,
        "count": str(top_k),
        "mkt": "zh-CN",
        "setLang": "zh-Hans",
        "textFormat": "Raw",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(BING_API_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []

        # Web pages
        for r in data.get("webPages", {}).get("value", [])[:top_k]:
            results.append({
                "title": r.get("name", ""),
                "snippet": r.get("snippet", ""),
                "url": r.get("url", ""),
                "source": "bing",
                "thumbnail": r.get("thumbnailUrl", "") or r.get("image", {}).get("thumbnail", {}).get("contentUrl", ""),
            })

        return results

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        append_log("WARN", f"Bing API timeout/connect: {str(e)[:80]}")
        return []
    except Exception as e:
        append_log("WARN", f"Bing API search failed: {str(e)[:80]}")
        return []


# ═══════════════════════════════════════════════════════════════════════
# Multi-Backend Search (racing — fastest response wins)
# ═══════════════════════════════════════════════════════════════════════

async def _multi_backend_search(
    query: str,
    top_k: int = 5,
    timeout: float = 5.0,
) -> list[dict]:
    """Race multiple search backends — first successful response wins.

    Priority (fastest wins, but quality-weighted):
      1. SerpAPI (Google — best quality, paid)
      2. Bing (good quality, free tier)
      3. DuckDuckGo HTML (free, may be blocked in some regions)
      4. DuckDuckGo Instant Answer (free, limited to encyclopedia)

    Uses asyncio.wait(FIRST_COMPLETED) for true racing.
    Falls back to next backend if the fastest returns empty.
    """
    all_results: list[dict] = []
    pending: set[asyncio.Task] = set()

    # Launch all available backends
    backends_launched: list[str] = []

    if settings.serpapi_key:
        backends_launched.append("serpapi")
        pending.add(asyncio.create_task(
            _serpapi_search(query, top_k=top_k, timeout=timeout),
            name="serpapi",
        ))

    if settings.bing_api_key:
        backends_launched.append("bing")
        pending.add(asyncio.create_task(
            _bing_search(query, top_k=top_k, timeout=timeout),
            name="bing",
        ))

    # DDG HTML: only launch when no paid API key available (free but slow/may be blocked)
    if not settings.serpapi_key and not settings.bing_api_key:
        backends_launched.append("ddg_html")
        pending.add(asyncio.create_task(
            _ddg_html_search(query, top_k=top_k, timeout=2.0),
            name="ddg_html",
        ))

    if not backends_launched:
        # No backends at all — try DDG instant answer as last resort
        backends_launched.append("ddg_ia")
        pending.add(asyncio.create_task(
            _ddg_instant_answer(query, top_k=top_k, timeout=2.0),
            name="ddg_ia",
        ))
        return []

    # Race: collect results from each backend as they complete
    remaining_timeout = timeout + 2.0
    while pending and remaining_timeout > 0:
        if len(pending) == 1:
            # Only one left — just await it directly
            for task in pending:
                try:
                    results = await asyncio.wait_for(task, timeout=remaining_timeout)
                    if results:
                        all_results.extend(results)
                        source = getattr(task, '_name', 'unknown')
                        append_log("DEBUG", f"Backend '{source}' returned {len(results)} results")
                except (asyncio.TimeoutError, Exception):
                    pass
            break

        done, pending = await asyncio.wait(
            pending,
            timeout=remaining_timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in done:
            source = getattr(task, '_name', task.get_name() if hasattr(task, 'get_name') else 'unknown')
            try:
                results = task.result()
                if results:
                    all_results.extend(results)
                    append_log("DEBUG", f"Backend '{source}' returned {len(results)} results")
                    # Got good results from one backend — cancel remaining
                    for p in pending:
                        p.cancel()
                    pending.clear()
                    break
                else:
                    append_log("DEBUG", f"Backend '{source}' returned no results, trying next...")
            except Exception as e:
                append_log("DEBUG", f"Backend '{source}' failed: {str(e)[:60]}")

        if not all_results:
            remaining_timeout -= 1.0  # Approximate

    return all_results
# Uses DDG's HTML search endpoint for real web search results.
# The Instant Answer API is used as a supplement for knowledge results.
# ═══════════════════════════════════════════════════════════════════════

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DDG_API = "https://api.duckduckgo.com/"

# Regex patterns for parsing DDG HTML search results
_DDG_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]+)</a>'
)
_DDG_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*)*)</a>'
)
_DDG_URL_RE = re.compile(
    r'<a[^>]*class="result__url"[^>]*>([^<]+)</a>'
)


def _parse_ddg_html(html: str, top_k: int = 8) -> list[dict]:
    """Parse DuckDuckGo HTML search results into structured dicts."""
    results: list[dict] = []

    # Split into individual result blocks
    # DDG HTML results are in divs with class "result" or "results_links"
    blocks = re.split(r'<div[^>]*class="[^"]*result', html)[1:]  # Skip first (before first result)

    for block in blocks[:top_k * 2]:
        # Extract link URL
        link_match = re.search(
            r'<a[^>]*class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]+)</a>',
            block,
        )
        if not link_match:
            continue

        url = link_match.group(1).strip()
        title = link_match.group(2).strip()

        # Skip non-product links
        if not url.startswith("http"):
            continue

        # Extract snippet
        snippet = ""
        snippet_match = re.search(
            r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            block,
            re.DOTALL,
        )
        if snippet_match:
            # Clean HTML tags from snippet
            raw_snippet = snippet_match.group(1)
            snippet = re.sub(r'<[^>]+>', '', raw_snippet).strip()
            snippet = html_mod.unescape(snippet)

        if title:
            results.append({
                "title": html_mod.unescape(title),
                "snippet": snippet,
                "url": url,
                "source": "duckduckgo_html",
            })

    return results[:top_k]


async def _ddg_html_search(query: str, top_k: int = 5, timeout: float = 2.0) -> list[dict]:
    """Search via DuckDuckGo HTML endpoint for real web results.

    This uses DDG's non-JS HTML search which returns actual search engine
    results (unlike the Instant Answer API which only returns encyclopedia data).
    """
    params = {
        "q": query,
        "kl": "cn-zh",  # Chinese region
    }
    headers = {
        **_BROWSER_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            resp = await client.post(DDG_HTML_URL, data=params)
            if resp.status_code != 200:
                append_log("WARN", f"DDG HTML search returned {resp.status_code}")
                return []
            html_text = resp.text

        results = _parse_ddg_html(html_text, top_k)

        if results:
            append_log("DEBUG", f"DDG HTML search: {len(results)} results for '{query[:40]}'")
        return results

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        append_log("WARN", f"DDG HTML search timeout: {str(e)[:80]}")
        return []
    except Exception as e:
        append_log("WARN", f"DDG HTML search failed: {str(e)[:80]}")
        return []


async def _ddg_instant_answer(query: str, top_k: int = 5, timeout: float = 3.0) -> list[dict]:
    """Supplement: DuckDuckGo Instant Answer API for knowledge/shopping results."""
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "no_redirect": "1",
        "skip_disambig": "1",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=_BROWSER_HEADERS) as client:
            resp = await client.get(DDG_API, params=params)
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []

        # Abstract (instant answer)
        abstract = data.get("AbstractText", "")
        abstract_url = data.get("AbstractURL", "")
        if abstract and len(abstract) > 20:
            results.append({
                "title": data.get("Heading", query),
                "snippet": abstract,
                "url": abstract_url,
                "source": "duckduckgo",
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:top_k]:
            if isinstance(topic, dict):
                text = topic.get("Text", "")
                url = topic.get("FirstURL", "")
                if text and len(text) > 20:
                    results.append({
                        "title": url.split("/")[-1].replace("_", " ")[:80],
                        "snippet": text,
                        "url": url,
                        "source": "duckduckgo",
                    })

        # Also try Results array
        for r in data.get("Results", [])[:top_k]:
            snippet = r.get("Text", "") or r.get("snippet", "")
            url = r.get("FirstURL", "")
            if snippet and url and len(snippet) > 20:
                results.append({
                    "title": url.split("/")[-1].replace("_", " ")[:80],
                    "snippet": snippet,
                    "url": url,
                    "source": "duckduckgo",
                })

        return results

    except (httpx.TimeoutException, httpx.ConnectError) as e:
        append_log("WARN", f"DuckDuckGo Instant Answer timeout: {str(e)[:80]}")
        return []
    except Exception as e:
        append_log("WARN", f"DuckDuckGo Instant Answer failed: {str(e)[:80]}")
        return []


async def _ddg_search(query: str, top_k: int = 5, timeout: float = 5.0) -> list[dict]:
    """Combined DDG search: HTML results + Instant Answer supplement.

    Uses the HTML endpoint (real web search) as primary and supplements
    with the Instant Answer API for additional context.
    """
    # Primary: HTML search (real web results)
    html_results = await _ddg_html_search(query, top_k=top_k, timeout=timeout)

    # Supplement: Instant Answer API (runs in parallel for knowledge)
    if len(html_results) < top_k:
        try:
            ia_results = await _ddg_instant_answer(query, top_k=top_k, timeout=3.0)
            # Only add IA results that aren't duplicates
            seen_urls = {r.get("url") for r in html_results if r.get("url")}
            for r in ia_results:
                if r.get("url") not in seen_urls:
                    html_results.append(r)
                    seen_urls.add(r.get("url"))
        except Exception:
            pass

    return html_results[:top_k]


# ═══════════════════════════════════════════════════════════════════════
# Link & Price Extraction
# ═══════════════════════════════════════════════════════════════════════

def _extract_platform_links(
    results: list[dict],
    platform: str,
) -> list[dict]:
    """Extract product links for a specific platform from search results.

    Scans each result's URL and snippet for platform-specific product page URLs.
    """
    pattern = PLATFORM_LINK_PATTERNS.get(platform)
    if not pattern:
        return []

    products: list[dict] = []
    seen_urls: set[str] = set()

    for r in results:
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        title = r.get("title", "")

        # Try to find product links in the result URL itself
        if url:
            for match in pattern.finditer(url):
                product_url = match.group(0).rstrip(".,;:)")
                if product_url not in seen_urls:
                    seen_urls.add(product_url)
                    products.append({
                        "name": title or r.get("title", ""),
                        "title": title or r.get("title", ""),
                        "price": _extract_price(snippet),
                        "platform": platform,
                        "url": product_url,
                        "snippet": snippet[:200],
                    })

        # Also scan the snippet for product links
        if snippet:
            for match in pattern.finditer(snippet):
                product_url = match.group(0).rstrip(".,;:)")
                if product_url not in seen_urls:
                    seen_urls.add(product_url)
                    products.append({
                        "name": title or r.get("title", ""),
                        "title": title or r.get("title", ""),
                        "price": _extract_price(snippet),
                        "platform": platform,
                        "url": product_url,
                        "snippet": snippet[:200],
                    })

    return products


# ═══════════════════════════════════════════════════════════════════════
# Caching
# ═══════════════════════════════════════════════════════════════════════

# In-memory cache: key → (expiry_timestamp, results)
_mem_cache: dict[str, tuple[float, list[dict]]] = {}
_MEM_CACHE_TTL = 300  # 5 minutes
_MAX_CACHE_SIZE = 512


def _cache_key(query: str, platforms: tuple[str, ...]) -> str:
    """Generate a cache key from query and platform list."""
    raw = f"{query}|{'|'.join(sorted(platforms))}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> list[dict] | None:
    """Get cached results if not expired."""
    entry = _mem_cache.get(key)
    if entry:
        expiry, results = entry
        if time.time() < expiry:
            return results
        del _mem_cache[key]
    return None


def _cache_set(key: str, results: list[dict]) -> None:
    """Store results in memory cache with TTL. Evict oldest if cache is full."""
    # Evict oldest entries if at capacity
    if len(_mem_cache) >= _MAX_CACHE_SIZE:
        oldest = min(_mem_cache.items(), key=lambda x: x[1][0])
        del _mem_cache[oldest[0]]
    _mem_cache[key] = (time.time() + _MEM_CACHE_TTL, results)


async def _redis_cache_get(key: str) -> list[dict] | None:
    """Try to retrieve cached results from Redis."""
    try:
        from app.core.database import get_redis
        redis = await get_redis()
        if redis:
            raw = await redis.get(f"eva:ecom_web:{key}")
            if raw:
                return json.loads(raw)
    except Exception:
        pass
    return None


async def _redis_cache_set(key: str, results: list[dict], ttl: int = 600) -> None:
    """Store results in Redis cache."""
    try:
        from app.core.database import get_redis
        redis = await get_redis()
        if redis:
            await redis.setex(
                f"eva:ecom_web:{key}",
                ttl,
                json.dumps(results, ensure_ascii=False, default=str),
            )
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
# Main Public API
# ═══════════════════════════════════════════════════════════════════════

async def ecommerce_web_search(
    product_query: str,
    platforms: list[str] | None = None,
    top_k: int = 5,
    timeout: float = 6.0,
    fast_mode: bool = False,
) -> list[dict]:
    """Search e-commerce platforms for real product links via search engines.

    Searches Google (SerpAPI) or DuckDuckGo for product listings on major
    Chinese e-commerce platforms. Returns structured product data with
    real URLs, prices, and confidence scores.

    Args:
        product_query: The product to search for (Chinese or English)
        platforms: Which platforms to search (default: all 8, or top 4 in fast mode)
        top_k: Maximum number of products to return
        timeout: Total timeout in seconds
        fast_mode: Use fewer platforms and shorter timeout for fast response

    Returns:
        List of product dicts: {title, price, platform, url, confidence, source}
    """
    if fast_mode:
        platforms = platforms or FAST_PLATFORMS
        timeout = min(timeout, 4.0)
    else:
        platforms = platforms or DEFAULT_PLATFORMS

    t_start = time.perf_counter()

    # Check caches first
    ck = _cache_key(product_query, tuple(platforms))
    cached = _cache_get(ck)
    if cached is not None:
        append_log("DEBUG", f"ecom_web cache hit (memory): {product_query[:40]}")
        return cached

    # Try Redis cache
    redis_cached = await _redis_cache_get(ck)
    if redis_cached is not None:
        _cache_set(ck, redis_cached)  # Populate memory cache too
        append_log("DEBUG", f"ecom_web cache hit (redis): {product_query[:40]}")
        return redis_cached

    # ── Execute search: parallel price lookup + platform link search ──
    # Strategy:
    #   1. Google Shopping → REAL prices (always try if SerpAPI key available)
    #   2. Web search → platform links (SerpAPI/Bing/DDG)
    #   Run them in parallel, merge results.
    all_products: list[dict] = []
    broad_raw: list[dict] = []
    shopping_products: list[dict] = []

    # Launch parallel price + link searches
    async def _broad_search():
        if settings.serpapi_key:
            try:
                broad_query = f'"{product_query}" 价格 多少钱'
                return await asyncio.wait_for(
                    _serpapi_search(broad_query, top_k=5, timeout=min(timeout, 2.5)),
                    timeout=min(timeout, 3.0),
                )
            except asyncio.TimeoutError:
                pass
        elif settings.bing_api_key:
            try:
                return await asyncio.wait_for(
                    _bing_search(f'"{product_query}" 购买 价格', top_k=5, timeout=min(timeout, 4.0)),
                    timeout=min(timeout, 4.5),
                )
            except asyncio.TimeoutError:
                pass
        else:
            try:
                return await _ddg_instant_answer(
                    f"{product_query} 价格", top_k=6, timeout=2.5,
                )
            except Exception:
                pass
        return []

    # Run Google Shopping + Web Search in parallel for fastest real-price results
    search_tasks = [_broad_search()]
    if settings.serpapi_key:
        search_tasks.append(
            _serpapi_shopping_search(product_query, top_k=5, timeout=min(timeout, 3.0))
        )

    parallel_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    broad_raw = parallel_results[0] if not isinstance(parallel_results[0], Exception) else []
    shopping_products = parallel_results[1] if len(parallel_results) > 1 and not isinstance(parallel_results[1], Exception) else []

    if broad_raw:
        for platform in platforms:
            prods = _extract_platform_links(broad_raw, platform)
            all_products.extend(prods)

    # ── Extract price context from ALL sources ──
    price_hints = _extract_prices_from_snippets(broad_raw) if broad_raw else {}
    # Merge shopping price data (richer, more reliable)
    for sp in shopping_products:
        if sp.get("price", 0) > 0:
            # Use shopping results to enrich price hints across platforms
            source = sp.get("snippet", "") or sp.get("title", "")
            for plat_keyword in ["京东", "天猫", "淘宝", "得物", "拼多多"]:
                if plat_keyword in source:
                    if plat_keyword not in price_hints or sp["price"] > price_hints[plat_keyword].get("price", 0):
                        price_hints[plat_keyword] = {
                            "price": sp["price"],
                            "title": sp.get("title", "")[:60],
                            "thumbnail": sp.get("thumbnail", ""),
                        }
                    break
            else:
                # Generic price hint (platform unknown)
                if "average" not in price_hints:
                    price_hints["average"] = {"price": sp["price"], "title": sp.get("title", "")[:60]}

    if shopping_products:
        append_log("DEBUG", f"Google Shopping: {len(shopping_products)} priced products for '{product_query[:40]}'")

    # ── Normalize, score, and deduplicate ──
    seen_urls: set[str] = set()
    final_products: list[dict] = []

    for p in all_products:
        url = p.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        # Calculate confidence score
        has_api_key = bool(settings.serpapi_key or settings.bing_api_key)
        confidence = 60.0  # Base: real link from search engine
        if p.get("price", 0) > 0:
            confidence += 10.0  # Bonus: has price
        if has_api_key:
            confidence += 5.0   # Bonus: higher-quality backend
        if "item.jd.com" in url or "detail.tmall.com" in url:
            confidence += 10.0  # Bonus: JD/Tmall product detail page
        confidence = min(confidence, 90.0)

        final_products.append({
            "name": p.get("title", p.get("name", product_query)),
            "title": p.get("title", product_query),
            "price": p.get("price", 0.0),
            "platform": p.get("platform", ""),
            "url": url,
            "image_url": p.get("thumbnail", "") or p.get("image_url", ""),
            "confidence": round(confidence, 1),
            "source": "ecommerce_web",
            "snippet": p.get("snippet", ""),
        })

    # Sort by confidence (highest first), then by price (lowest first for priced items)
    final_products.sort(key=lambda x: (-x.get("confidence", 0), x.get("price", 999999)))

    result = final_products[:top_k]

    # Phase 4: Build final output with real prices where available
    has_real_links = any(
        any(d in p.get("url", "") for d in ["item.jd.com", "detail.tmall.com", "item.taobao.com"])
        for p in final_products
    )

    if has_real_links:
        # We have real product detail page links — return those directly
        result = final_products[:top_k]
    elif final_products:
        # Search results with extracted info — merge with enriched search URLs
        enriched_urls = _generate_search_urls(
            product_query, platforms, enrichment=price_hints,
        )
        # Merge, deduplicating by URL
        existing_urls = {p["url"] for p in final_products}
        for eu in enriched_urls:
            if eu["url"] not in existing_urls:
                final_products.append(eu)
        result = final_products[:top_k]
    else:
        # Nothing at all — generate search URLs with any price hints we found
        has_any_api = bool(settings.serpapi_key or settings.bing_api_key)
        if has_any_api:
            result = _generate_search_urls(product_query, platforms, enrichment=price_hints)
        else:
            result = []

    # Cache results (only cache real findings, not empty)
    if result:
        _cache_set(ck, result)
        asyncio.create_task(_redis_cache_set(ck, result))

    elapsed_ms = (time.perf_counter() - t_start) * 1000
    if settings.serpapi_key:
        backend_name = "serpapi"
    elif settings.bing_api_key:
        backend_name = "bing"
    else:
        backend_name = "duckduckgo"
    append_log(
        "INFO" if result else "DEBUG",
        f"[ecom_web] {backend_name} → {len(result)} products for "
        f"'{product_query[:40]}' ({elapsed_ms:.0f}ms)",
    )

    return result


def _generate_search_urls(
    query: str,
    platforms: list[str] | None = None,
    enrichment: dict[str, dict] | None = None,
) -> list[dict]:
    """Generate clickable search URLs enriched with real search data.

    Always works — builds real platform search URLs. When enrichment
    data is available from web search results, includes price context.

    Args:
        query: Product search query
        platforms: Which platforms to generate URLs for
        enrichment: Optional dict of {platform_name: {price, title}} from search results
    """
    platforms = platforms or DEFAULT_PLATFORMS
    enrichment = enrichment or {}
    results = []

    for plat in platforms:
        tmpl = PLATFORM_SEARCH_URLS.get(plat)
        if not tmpl:
            continue

        url = tmpl.format(quote(query))
        extra = enrichment.get(plat, {})
        price = extra.get("price", 0.0)
        snippet = extra.get("title", "")
        thumbnail = extra.get("thumbnail", "")

        # If this platform doesn't have a direct price, use average price from shopping
        if price == 0 and "average" in enrichment:
            price = enrichment["average"].get("price", 0.0)
            snippet = snippet or enrichment["average"].get("title", "")

        # Build descriptive title — always include real price when available
        if price > 0:
            title = f"{query}  |  {plat}  ¥{price:,.0f}"
        else:
            title = query

        results.append({
            "name": title,        # Primary name field for _enrich_product
            "title": title,       # Also set title for display
            "price": price,       # REAL price from shopping/search
            "platform": plat,
            "url": url,
            "image_url": thumbnail,
            "confidence": 25.0 if price > 0 else 15.0,  # Higher confidence when price confirmed
            "source": "ecommerce_web",
        })

    return results


def _extract_prices_from_snippets(results: list[dict]) -> dict[str, dict]:
    """Parse search snippets to find platform-specific price mentions.

    Returns dict like: {"京东": {"price": 9499.0, "title": "iPhone 16 Pro Max"}}
    """
    platform_hints: dict[str, dict] = {}

    # Platform name patterns in Chinese
    plat_patterns = {
        "京东": re.compile(r'京东|jd\.com', re.I),
        "天猫": re.compile(r'天猫|tmall', re.I),
        "淘宝": re.compile(r'淘宝|taobao', re.I),
        "得物": re.compile(r'得物|dewu', re.I),
        "拼多多": re.compile(r'拼多多|pinduoduo|yangkeduo', re.I),
    }

    for r in results:
        snippet = r.get("snippet", "")
        title = r.get("title", "")
        combined = f"{title} {snippet}"
        price = _extract_price(combined)

        for plat, pattern in plat_patterns.items():
            if pattern.search(combined):
                if plat not in platform_hints or price > platform_hints[plat].get("price", 0):
                    platform_hints[plat] = {
                        "price": price,
                        "title": title[:60],
                    }

    return platform_hints


# ═══════════════════════════════════════════════════════════════════════
# Fast single-platform search (for quick price checks)
# ═══════════════════════════════════════════════════════════════════════

async def quick_ecommerce_search(
    query: str,
    platforms: list[str] | None = None,
    timeout: float = 3.0,
) -> list[dict]:
    """Fast search on top platforms only. Returns best-matching products."""
    platforms = platforms or FAST_PLATFORMS
    return await ecommerce_web_search(
        query,
        platforms=platforms,
        top_k=3,
        timeout=timeout,
        fast_mode=True,
    )
