"""LLM call utility — race-based with streaming callback + model routing.

v4 optimizations:
- Dynamic provider routing via model_router (simple→Groq, complex→DeepSeek)
- Redis cache layer with in-memory fallback
- Token estimation for prompt size monitoring
- Streaming callback unchanged (progressive token delivery)
"""

import asyncio
import hashlib
import time
from typing import Callable, Awaitable, Sequence

from app.core.llm import get_llm_client, get_model_name, track_token_usage, track_model_latency
from app.api.v1.admin import append_log

# Default fallback when no router is used
DEFAULT_PROVIDERS = ["groq", "glm_flash", "ernie35", "deepseek"]
MAX_ATTEMPTS = 4
_LLM_CALL_TIMEOUT = 2.5  # per-provider timeout

# ── In-memory fallback cache (always available) ──
_cache: dict[str, tuple[float, str, str]] = {}
_CACHE_TTL = 300


def _cache_key(system_prompt: str, user_message: str) -> str:
    return hashlib.sha256(f"{system_prompt}|||{user_message}".encode()).hexdigest()


# ── Token estimation (fast, no API call) ──
def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 chars per token for Chinese, ~3 for English."""
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    other = len(text) - chinese
    return int(chinese * 0.6 + other * 0.25)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens for a list of messages."""
    return sum(estimate_tokens(m.get("content", "")) for m in messages) + len(messages) * 4


async def llm_call(
    *,
    system_prompt: str,
    user_message: str,
    max_tokens: int = 400,
    temperature: float = 0.3,
    user_id: str = "",
    node_name: str = "agent",
    response_format: dict | None = None,
    stream_callback: Callable[[str], Awaitable[None]] | None = None,
    bypass_cache: bool = False,
    providers: Sequence[str] | None = None,
    per_provider_timeout: float | None = None,
) -> tuple[str, str, float]:
    """Race multiple providers, return first successful response.

    When stream_callback is provided, tokens are delivered progressively
    via the callback BEFORE this function returns.

    Args:
        providers: Ordered list of provider keys to try. Defaults to DEFAULT_PROVIDERS.
        per_provider_timeout: Timeout per provider in seconds. Defaults to _LLM_CALL_TIMEOUT.

    Returns:
        (content, provider_name, elapsed_ms)
    """
    ck = _cache_key(system_prompt, user_message)

    # ── 1. Redis cache check (with in-memory fallback) ──
    if not bypass_cache:
        try:
            from app.cache.redis_cache import get_cache
            cache_layer = await get_cache()
            if (cached := await cache_layer.get(f"eva:llm:{ck}")):
                provider = cached.get("p", "cache")
                content = cached.get("c", "")
                append_log("INFO", f"{node_name} 命中Redis缓存 (provider={provider})")
                if stream_callback:
                    await stream_callback(content)
                return content, provider, 0.0
        except Exception:
            pass

    # ── 2. In-memory cache check ──
    if not bypass_cache and ck in _cache:
        expiry, content, provider = _cache[ck]
        if time.time() < expiry:
            append_log("INFO", f"{node_name} 命中内存缓存 (provider={provider})")
            if stream_callback:
                await stream_callback(content)
            return content, provider, 0.0
        del _cache[ck]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    # Token estimate for logging
    est_tokens = estimate_messages_tokens(messages)

    # ── 3. Determine providers ──
    provider_list = list(providers or DEFAULT_PROVIDERS)
    if not provider_list:
        provider_list = list(DEFAULT_PROVIDERS)
    provider_list = provider_list[:MAX_ATTEMPTS]
    timeout = per_provider_timeout or _LLM_CALL_TIMEOUT

    async def _try_provider(provider: str) -> tuple[str, str] | None:
        try:
            client = get_llm_client(provider)
            model = get_model_name(provider)

            kwargs: dict = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if response_format is not None:
                kwargs["response_format"] = response_format

            use_stream = stream_callback is not None
            if use_stream:
                kwargs["stream"] = True

            t0 = time.perf_counter()

            if use_stream:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=timeout,
                )
                chunks: list[str] = []
                buffer: list[str] = []
                MIN_CHUNK_SIZE = 3  # 合并小块（至少3字符才发送回调）

                async for chunk in resp:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        chunks.append(delta.content)
                        buffer.append(delta.content)
                        # 缓冲足够大或遇到标点时才发送回调
                        combined = "".join(buffer)
                        if len(combined) >= MIN_CHUNK_SIZE or any(
                            punct in combined for punct in ("。", "！", "？", "\n", "，", ".", "!", "?", ",")
                        ):
                            await stream_callback(combined)
                            buffer.clear()

                # 发送剩余缓冲
                if buffer:
                    await stream_callback("".join(buffer))

                content = "".join(chunks)
            else:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=timeout,
                )
                content = resp.choices[0].message.content or ""
                if resp.usage:
                    track_token_usage(user_id, provider, resp.usage.total_tokens)
                    actual_tokens = resp.usage.total_tokens
                    append_log(
                        "DEBUG",
                        f"{node_name} tokens: est={est_tokens} actual={actual_tokens} provider={provider}",
                    )

            elapsed_ms = (time.perf_counter() - t0) * 1000
            track_model_latency(provider, elapsed_ms)

            # ── Store in both caches ──
            _cache[ck] = (time.time() + _CACHE_TTL, content, provider)
            try:
                from app.cache.redis_cache import get_cache
                cache_layer = await get_cache()
                await cache_layer.set(
                    f"eva:llm:{ck}",
                    {"c": content, "p": provider, "t": elapsed_ms},
                    ttl=_CACHE_TTL,
                )
            except Exception:
                pass

            return content, provider
        except (asyncio.TimeoutError, Exception):
            return None

    t_total = time.perf_counter()

    # ── 4. Race providers ──
    tasks = [asyncio.create_task(_try_provider(p)) for p in provider_list]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            result = t.result()
            if result is not None:
                for pt in pending:
                    pt.cancel()
                content, provider = result
                elapsed_ms = (time.perf_counter() - t_total) * 1000
                append_log(
                    "SUCCESS",
                    f"{node_name} 完成 ({elapsed_ms:.0f}ms, est_tokens={est_tokens}) "
                    f"provider={provider} route={'→'.join(provider_list[:3])}",
                )
                return content, provider, elapsed_ms

        # Second wave
        if pending:
            done2, pending2 = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED, timeout=2.0,
            )
            for t in done2:
                result = t.result()
                if result is not None:
                    for pt in pending2:
                        pt.cancel()
                    content, provider = result
                    elapsed_ms = (time.perf_counter() - t_total) * 1000
                    return content, provider, elapsed_ms
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    elapsed_ms = (time.perf_counter() - t_total) * 1000
    append_log("WARN", f"{node_name} 模型调用全部失败 ({elapsed_ms:.0f}ms)")
    return "", "", elapsed_ms


# ═══════════════════════════════════════════════════════════════════════
# Function Calling — 结构化工具调用
# ═══════════════════════════════════════════════════════════════════════

async def llm_call_with_tools(
    *,
    system_prompt: str,
    user_message: str,
    tools: list[dict],
    max_tokens: int = 600,
    temperature: float = 0.2,
    user_id: str = "",
    node_name: str = "tool_agent",
    providers: Sequence[str] | None = None,
    per_provider_timeout: float | None = None,
    tool_choice: str = "auto",
) -> tuple[list[dict], str, float]:
    """带 Function Calling 的 LLM 调用。

    支持 OpenAI-compatible 的 tool_use 功能。
    所有 8 个 provider（DeepSeek, OpenAI, Groq, GLM, ERNIE）均支持。

    Args:
        system_prompt: 系统提示
        user_message: 用户消息
        tools: OpenAI 格式的 tools schema 列表
        max_tokens: 最大输出 token
        temperature: 温度
        user_id: 用户ID
        node_name: 日志节点名
        providers: provider 列表
        per_provider_timeout: 每个 provider 的超时
        tool_choice: "auto" | "none" | "required" | 特定 tool

    Returns:
        (tool_calls, provider_name, elapsed_ms)
        tool_calls: [{"id": "...", "function": {"name": "...", "arguments": "..."}}, ...]
        如果 LLM 没有调用工具，返回空列表
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    provider_list = list(providers or DEFAULT_PROVIDERS)
    if not provider_list:
        provider_list = list(DEFAULT_PROVIDERS)
    provider_list = provider_list[:MAX_ATTEMPTS]
    timeout = per_provider_timeout or _LLM_CALL_TIMEOUT

    est_tokens = estimate_messages_tokens(messages)

    async def _try_provider(provider: str) -> tuple[list[dict], str] | None:
        try:
            client = get_llm_client(provider)
            model = get_model_name(provider)

            kwargs: dict = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "tools": tools,
                "tool_choice": tool_choice,
            }

            t0 = time.perf_counter()
            resp = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=timeout,
            )

            choice = resp.choices[0] if resp.choices else None
            if not choice:
                return None

            # 检查是否有 tool_calls
            msg = choice.message
            if msg.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]

                if resp.usage:
                    track_token_usage(user_id, provider, resp.usage.total_tokens)

                elapsed_ms = (time.perf_counter() - t0) * 1000
                track_model_latency(provider, elapsed_ms)

                append_log(
                    "SUCCESS",
                    f"{node_name} tool_call ({elapsed_ms:.0f}ms) "
                    f"provider={provider} tools={[tc['function']['name'] for tc in tool_calls]}",
                )
                return tool_calls, provider

            # 没有 tool_calls — 返回空（LLM 选择不调用工具）
            if msg.content:
                append_log(
                    "INFO",
                    f"{node_name} LLM 选择不调用工具，返回文本: "
                    f"{msg.content[:80]}...",
                )
            return [], provider

        except (asyncio.TimeoutError, Exception):
            return None

    t_total = time.perf_counter()

    # Race providers
    tasks = [asyncio.create_task(_try_provider(p)) for p in provider_list]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            result = t.result()
            if result is not None:
                for pt in pending:
                    pt.cancel()
                tool_calls, provider = result
                elapsed_ms = (time.perf_counter() - t_total) * 1000
                return tool_calls, provider, elapsed_ms

        # Second wave
        if pending:
            done2, pending2 = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED, timeout=2.0,
            )
            for t in done2:
                result = t.result()
                if result is not None:
                    for pt in pending2:
                        pt.cancel()
                    tool_calls, provider = result
                    elapsed_ms = (time.perf_counter() - t_total) * 1000
                    return tool_calls, provider, elapsed_ms
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    elapsed_ms = (time.perf_counter() - t_total) * 1000
    append_log("WARN", f"{node_name} tool_call 全部失败 ({elapsed_ms:.0f}ms)")
    return [], "", elapsed_ms
