"""SerpAPI Product Search — Real product data with images from Google Shopping.

Integrates with SerpAPI to fetch real product listings from Google Shopping:
- Real product images (thumbnails from Google Shopping)
- Real prices (current market prices)
- Store/seller attribution (京东, 天猫, etc.)
- Review ratings and counts
- Clickable product links

Usage:
    from app.agent.serpapi_search import serpapi_product_search

    results = await serpapi_product_search("iPhone 16 Pro 256GB", top_k=5)
"""

import asyncio
import hashlib
import json
import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.api.v1.admin import append_log
from app.config import get_settings

settings = get_settings()

SERPAPI_URL = "https://serpapi.com/search"

# Cache
_cache: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 600  # 10 minutes


def _cache_key(query: str) -> str:
    return f"serpapi:{hashlib.sha256(query.encode()).hexdigest()[:16]}"


async def serpapi_product_search(
    query: str,
    top_k: int = 5,
    timeout: float = 10.0,
) -> list[dict]:
    """Search Google Shopping via SerpAPI for real product data.

    Returns products with:
      - name: Product title
      - price: Current price (float)
      - original_price: Old price if on sale
      - platform: Store/seller name
      - url: Product link
      - image_url: Real product thumbnail from Google Shopping
      - rating: Average rating (0-5)
      - review_count: Number of reviews
      - source: "serpapi_shopping"
      - confidence: 60-85% (based on data completeness)
    """
    api_key = getattr(settings, "serpapi_key", "") or ""
    if not api_key:
        append_log("WARN", "SerpAPI key not configured, skipping product search")
        return []

    # Check cache
    ck = _cache_key(query)
    if ck in _cache:
        expiry, cached = _cache[ck]
        if time.time() < expiry:
            append_log("DEBUG", f"SerpAPI cache hit: {query[:40]}")
            return cached[:top_k]

    t0 = time.perf_counter()

    # ── Phase 1: Google Shopping search ──
    params = {
        "engine": "google_shopping",
        "q": query,
        "api_key": api_key,
        "gl": "cn",
        "hl": "zh-cn",
        "num": str(min(top_k + 5, 20)),
    }

    shopping_results: list[dict] = []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(SERPAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        raw = data.get("shopping_results", [])
        append_log("INFO", f"SerpAPI Google Shopping: {len(raw)} raw results for '{query[:40]}'")

        for item in raw:
            # Extract price
            price = item.get("extracted_price", 0.0)
            if not price:
                price_str = item.get("price", "0")
                try:
                    price = float(price_str.replace("¥", "").replace(",", "").strip() or 0)
                except (ValueError, TypeError):
                    price = 0.0

            old_price = item.get("extracted_old_price", 0.0)
            if not old_price:
                old_str = item.get("old_price", "")
                try:
                    old_price = float(old_str.replace("¥", "").replace(",", "").strip() or 0)
                except (ValueError, TypeError):
                    old_price = 0.0

            # Rating and reviews
            rating = item.get("rating", None)
            review_count = item.get("reviews", 0)

            # Product link
            url = item.get("product_link", "")
            source_name = item.get("source", "Google Shopping")

            # Determine confidence based on data completeness
            confidence = 60.0  # Base confidence for SerpAPI data
            if price > 0:
                confidence += 10
            if rating:
                confidence += 8
            if review_count > 0:
                confidence += 5
            if url:
                confidence += 5
            confidence = min(confidence, 85.0)

            product = {
                "name": item.get("title", query),
                "price": price,
                "original_price": old_price if old_price > price else price,
                "platform": source_name,
                "url": url,
                "image_url": item.get("thumbnail", ""),  # Real image from Google Shopping!
                "rating": float(rating) if rating else None,
                "review_count": review_count,
                "source": "serpapi_shopping",
                "confidence": confidence,
                "shipping": item.get("shipping", ""),
                "tag": item.get("tag", ""),  # e.g., "11% OFF"
            }
            shopping_results.append(product)

    except httpx.HTTPStatusError as e:
        append_log("ERROR", f"SerpAPI HTTP error: {e.response.status_code} - {str(e)[:100]}")
    except (httpx.TimeoutException, asyncio.TimeoutError):
        append_log("WARN", f"SerpAPI timeout for '{query[:40]}'")
    except Exception as e:
        append_log("ERROR", f"SerpAPI unexpected error: {type(e).__name__}: {str(e)[:100]}")

    # ── Phase 2: If shopping results are sparse, try organic search for reviews ──
    if len(shopping_results) < 3:
        try:
            review_params = {
                "engine": "google",
                "q": f"{query} 评测 口碑 评价",
                "api_key": api_key,
                "gl": "cn",
                "hl": "zh-cn",
                "num": "5",
            }
            async with httpx.AsyncClient(timeout=min(timeout, 8.0)) as client:
                review_resp = await client.get(SERPAPI_URL, params=review_params)
                review_resp.raise_for_status()
                review_data = review_resp.json()

            for r in review_data.get("organic_results", [])[:3]:
                if r.get("snippet"):
                    product = {
                        "name": r.get("title", query),
                        "price": 0.0,
                        "original_price": 0.0,
                        "platform": r.get("source", "Web Review"),
                        "url": r.get("link", ""),
                        "image_url": "",  # Organic results don't have thumbnails
                        "rating": None,
                        "review_count": 0,
                        "review_snippet": r.get("snippet", "")[:300],
                        "source": "serpapi_web",
                        "confidence": 40.0,
                    }
                    # Avoid duplicates
                    existing_names = {p["name"].lower() for p in shopping_results}
                    if product["name"].lower() not in existing_names:
                        shopping_results.append(product)

            append_log("DEBUG", f"SerpAPI organic: added review results, total={len(shopping_results)}")
        except Exception:
            pass

    elapsed_ms = (time.perf_counter() - t0) * 1000
    append_log(
        "SUCCESS" if shopping_results else "WARN",
        f"SerpAPI search complete: {len(shopping_results)} results ({elapsed_ms:.0f}ms)",
    )

    # Cache results
    if shopping_results:
        _cache[ck] = (time.time() + _CACHE_TTL, shopping_results)

    return shopping_results[:top_k]


async def serpapi_image_search(
    query: str,
    top_k: int = 3,
    timeout: float = 8.0,
) -> list[str]:
    """Search for real product images via Google Images.

    Returns list of image URLs.
    """
    api_key = getattr(settings, "serpapi_key", "") or ""
    if not api_key:
        return []

    try:
        params = {
            "engine": "google_images",
            "q": f"{query} 商品",
            "api_key": api_key,
            "gl": "cn",
            "hl": "zh-cn",
            "num": str(top_k),
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(SERPAPI_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        images = []
        for img in data.get("images_results", [])[:top_k]:
            original = img.get("original", "")
            if original and original.startswith("http"):
                images.append(original)

        return images

    except Exception as e:
        append_log("WARN", f"SerpAPI image search failed: {str(e)[:80]}")
        return []
