"""Web Search Tool — 实时网络搜索

数据源: DuckDuckGo + SerpAPI（通过 hybrid/web_search.py）
"""

from app.tools.schema import ToolResult, ToolStatus
from app.tools.registry import registry


@registry.register(
    name="web_search",
    description="实时搜索互联网获取最新信息。适用于价格查询、新品发布、新闻动态等需要最新数据的场景。",
    category="external",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数，默认5",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)
async def search_web(query: str, max_results: int = 5) -> ToolResult:
    """实时网络搜索"""
    try:
        from app.hybrid.web_search import web_search as hybrid_web_search

        result = await hybrid_web_search(query)

        if not result.success or not result.evidence:
            return ToolResult.partial(
                tool="web_search",
                data=[],
                confidence=0.1,
                source="web_search",
                error="网络搜索未返回有效结果",
            )

        data = []
        for ev in result.evidence[:max_results]:
            data.append({
                "content": ev.content[:500],
                "url": ev.url or "",
                "relevance": ev.relevance_score,
                "freshness_days": ev.freshness_days,
            })

        confidence = min(
            sum(ev.relevance_score for ev in result.evidence[:max_results])
            / max(len(result.evidence[:max_results]), 1),
            0.85,
        )

        return ToolResult.success(
            tool="web_search",
            data=data,
            confidence=confidence,
            source="web_search",
            total_results=len(data),
            latency_ms=result.latency_ms,
        )

    except ImportError:
        return ToolResult.failed(
            tool="web_search",
            error="Web搜索模块不可用，请检查依赖配置",
        )
    except Exception as e:
        return ToolResult.failed(
            tool="web_search",
            error=f"网络搜索失败: {str(e)[:200]}",
        )
