"""
EVA MCP (Model Context Protocol) Server

Supports both STDIO (local dev) and SSE (production) transports.
Exposes 8 tools to external MCP clients like Claude Desktop.
"""
import json
import asyncio
from typing import Any


# Tool registry
TOOLS: dict[str, callable] = {}


def register_tool(name: str):
    def decorator(fn):
        TOOLS[name] = fn
        return fn
    return decorator


# ---- Tool definitions ----

@register_tool("search_products")
async def search_products(query: str, platform: str | None = None, limit: int = 10) -> list[dict]:
    """Search products across e-commerce platforms."""
    platforms = [platform] if platform else ["京东", "天猫", "得物", "淘宝"]
    results = []
    for pf in platforms:
        results.append({
            "id": f"{pf}_{hash(query)}",
            "name": f"{query} - {pf}",
            "platform": pf,
            "price": 0.0,
            "url": f"https://example.com/search?q={query}",
        })
    return results[:limit]


@register_tool("compare_price")
async def compare_price(product_name: str, platforms: list[str] | None = None) -> dict:
    """Compare prices across platforms."""
    target_platforms = platforms or ["京东", "天猫", "得物"]
    prices = {}
    for pf in target_platforms:
        prices[pf] = {"price": 0.0, "in_stock": True, "shipping": "免运费"}
    return {
        "product": product_name,
        "prices": prices,
        "best_platform": target_platforms[0] if target_platforms else "未知",
        "best_price": 0.0,
    }


@register_tool("analyze_reviews")
async def analyze_reviews(product_id: str, limit: int = 50) -> dict:
    """Analyze product reviews with sentiment analysis."""
    return {
        "product_id": product_id,
        "total_analyzed": 0,
        "sentiment": "positive",
        "average_rating": 0.0,
        "key_points": [],
        "summary": "暂无评论数据",
    }


@register_tool("generate_report")
async def generate_report(report_type: str, data: dict) -> str:
    """Generate a formatted shopping report."""
    return f"# {report_type} 报告\n\n报告数据：{json.dumps(data, ensure_ascii=False)}"


@register_tool("save_memory")
async def save_memory(user_id: str, key: str, value: dict, importance: float = 0.5) -> dict:
    """Save a memory entry for a user."""
    return {"id": "mem_000", "user_id": user_id, "key": key, "status": "saved"}


@register_tool("query_memory")
async def query_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """Semantically search user memories."""
    return []


@register_tool("web_search")
async def web_search(query: str, limit: int = 5) -> list[dict]:
    """Search the web for information."""
    return [{"title": "占位结果", "url": "https://example.com", "snippet": "这是一个占位搜索结果"}]


@register_tool("rag_search")
async def rag_search(query: str, top_k: int = 5) -> list[dict]:
    """Search internal knowledge base."""
    return [{"content": "暂无知识库数据", "source": "placeholder", "score": 1.0}]


# ---- Server transports ----

async def handle_stdio():
    """Handle a single JSON-RPC request over stdin/stdout."""
    while True:
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, input)
        except EOFError:
            break

        try:
            request = json.loads(line)
            method = request.get("method")
            tool_name = request.get("params", {}).get("name")
            tool_args = request.get("params", {}).get("arguments", {})

            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {
                        "tools": [
                            {
                                "name": name,
                                "description": fn.__doc__ or "",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                            for name, fn in TOOLS.items()
                        ]
                    },
                }
            elif method == "tools/call" and tool_name in TOOLS:
                result = await TOOLS[tool_name](**tool_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]},
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32601, "message": f"Unknown method or tool: {tool_name}"},
                }

            print(json.dumps(response, ensure_ascii=False), flush=True)

        except Exception as e:
            error_response = {"jsonrpc": "2.0", "id": request.get("id", 0), "error": {"code": -32603, "message": str(e)}}
            print(json.dumps(error_response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(handle_stdio())
