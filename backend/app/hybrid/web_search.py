"""Web Search integration for EVA Hybrid AI.

Provides real-time web search capability to resolve time-sensitive queries
and supplement RAG results when knowledge base is insufficient.

Backends (auto-select):
  - DuckDuckGo Instant Answer API (free, no key required)
  - SerpAPI (requires SERPAPI_KEY env var, higher quality)

Usage:
    from app.hybrid.web_search import web_search

    results = await web_search("iPhone 16 最新价格 2025")
"""

import asyncio
import hashlib
import json
import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.hybrid.types import SourceEvidence, SourceResult, SourceType
from app.api.v1.admin import append_log
from app.config import get_settings

settings = get_settings()

# ═══════════════════════════════════════════════════════════════════════
# DuckDuckGo Instant Answer API
# ═══════════════════════════════════════════════════════════════════════

DDG_API = "https://api.duckduckgo.com/"

# ═══════════════════════════════════════════════════════════════════════
# SerpAPI (optional, higher quality)
# ═══════════════════════════════════════════════════════════════════════

SERPAPI_URL = "https://serpapi.com/search"


async def _ddg_search(query: str, top_k: int = 5, timeout: float = 8.0) -> list[dict]:
    """Search DuckDuckGo Instant Answer API."""
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "no_redirect": "1",
        "skip_disambig": "1",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(DDG_API, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict] = []

    # Abstract (instant answer)
    abstract = data.get("AbstractText", "")
    if abstract and len(abstract) > 20:
        results.append({
            "title": data.get("Heading", query),
            "snippet": abstract,
            "url": data.get("AbstractURL", ""),
            "source": data.get("AbstractSource", "DuckDuckGo"),
        })

    # Related topics
    for topic in data.get("RelatedTopics", [])[:top_k]:
        if isinstance(topic, dict):
            text = topic.get("Text", "")
            if text and len(text) > 20:
                results.append({
                    "title": topic.get("FirstURL", "").split("/")[-1].replace("_", " ")[:80],
                    "snippet": text,
                    "url": topic.get("FirstURL", ""),
                    "source": "DuckDuckGo",
                })

    # Results (if available)
    for r in data.get("Results", [])[:top_k]:
        snippet = r.get("Text", "") or r.get("snippet", "")
        if snippet and len(snippet) > 20:
            results.append({
                "title": r.get("FirstURL", "").split("/")[-1].replace("_", " ")[:80],
                "snippet": snippet,
                "url": r.get("FirstURL", ""),
                "source": "DuckDuckGo",
            })

    return results[:top_k]


async def _serpapi_search(query: str, top_k: int = 5, timeout: float = 10.0) -> list[dict]:
    """Search via SerpAPI (requires SERPAPI_KEY)."""
    api_key = getattr(settings, "SERPAPI_KEY", None) or ""
    if not api_key:
        return []

    params = {
        "q": query,
        "api_key": api_key,
        "engine": "google",
        "num": str(top_k),
        "gl": "cn",   # Chinese results
        "hl": "zh-cn",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(SERPAPI_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    results: list[dict] = []

    # Organic results
    for r in data.get("organic_results", [])[:top_k]:
        results.append({
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
            "url": r.get("link", ""),
            "source": r.get("source", "Google"),
        })

    # Knowledge graph
    kg = data.get("knowledge_graph", {})
    if kg:
        desc = kg.get("description", "")
        if desc:
            results.insert(0, {
                "title": kg.get("title", query),
                "snippet": desc,
                "url": kg.get("website", ""),
                "source": "Knowledge Graph",
            })

    return results


# ═══════════════════════════════════════════════════════════════════════
# Result caching
# ═══════════════════════════════════════════════════════════════════════

_web_cache: dict[str, tuple[float, list[dict]]] = {}
_WEB_CACHE_TTL = 300  # 5 minutes


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

async def web_search(
    query: str,
    top_k: int = 5,
    timeout: float = 10.0,
    use_cache: bool = True,
) -> SourceResult:
    """Execute web search and return structured results.

    Uses SerpAPI if SERPAPI_KEY is set, otherwise falls back to DuckDuckGo.

    Returns a SourceResult with evidence list.
    """
    t0 = time.perf_counter()

    # Cache check
    ck = _cache_key(query)
    if use_cache and ck in _web_cache:
        expiry, cached = _web_cache[ck]
        if time.time() < expiry:
            append_log("DEBUG", f"web_search cache hit: {query[:40]}")
            evidence = [
                SourceEvidence(
                    source=SourceType.WEB,
                    content=r.get("snippet", ""),
                    relevance_score=0.7,
                    url=r.get("url", ""),
                    authority="community",
                )
                for r in cached
            ]
            return SourceResult(
                source=SourceType.WEB,
                success=len(evidence) > 0,
                evidence=evidence,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

    # Try SerpAPI first (higher quality)
    raw_results: list[dict] = []
    backend_used = "none"

    serpapi_key = getattr(settings, "SERPAPI_KEY", None)
    if serpapi_key:
        try:
            raw_results = await _serpapi_search(query, top_k=top_k, timeout=timeout)
            backend_used = "serpapi"
            append_log("DEBUG", f"SerpAPI search: {len(raw_results)} results for '{query[:40]}'")
        except Exception as e:
            append_log("WARN", f"SerpAPI search failed: {str(e)[:80]}")

    # Fallback to DuckDuckGo
    if not raw_results:
        try:
            raw_results = await _ddg_search(query, top_k=top_k, timeout=timeout)
            backend_used = "duckduckgo"
            append_log("DEBUG", f"DuckDuckGo search: {len(raw_results)} results for '{query[:40]}'")
        except Exception as e:
            append_log("ERROR", f"Web search failed completely: {str(e)[:80]}")
            return SourceResult(
                source=SourceType.WEB,
                success=False,
                error=f"All web search backends failed: {str(e)[:80]}",
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

    # Cache results
    if raw_results:
        _web_cache[ck] = (time.time() + _WEB_CACHE_TTL, raw_results)

    # Build evidence
    evidence = []
    for r in raw_results[:top_k]:
        evidence.append(SourceEvidence(
            source=SourceType.WEB,
            content=f"【{r.get('title', 'Web结果')}】{r.get('snippet', '')}",
            relevance_score=0.6,
            freshness_days=0,  # Web results are fresh
            authority="community",
            url=r.get("url", ""),
        ))

    latency_ms = (time.perf_counter() - t0) * 1000

    return SourceResult(
        source=SourceType.WEB,
        success=len(evidence) > 0,
        evidence=evidence,
        latency_ms=latency_ms,
    )


async def web_search_raw(
    query: str,
    top_k: int = 5,
    timeout: float = 10.0,
) -> list[dict]:
    """Lightweight web search returning raw dicts (for inline use in pipeline)."""
    result = await web_search(query, top_k=top_k, timeout=timeout)
    if not result.success:
        return []

    return [
        {
            "title": ev.url.split("/")[-1][:80] if ev.url else "Web来源",
            "content": ev.content,
            "url": ev.url,
            "source": "web",
            "score": ev.relevance_score,
            "freshness_days": ev.freshness_days,
        }
        for ev in result.evidence
    ]
