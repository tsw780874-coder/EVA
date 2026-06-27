"""LLM call utility — race-based with streaming callback + model routing.

v4 optimizations:
- Dynamic provider routing via model_router (simple→Groq, complex→DeepSeek)
- Redis cache layer with in-memory fallback
- Token estimation for prompt size monitoring
- Streaming callback unchanged (progressive token delivery)
"""

import asyncio
import hashlib
import json
import time
from typing import Callable, Awaitable, Sequence

from app.core.llm import get_llm_client, get_model_name, track_token_usage, track_model_latency
from app.api.v1.admin import append_log

# Default providers — ALL are tried simultaneously (true parallel race, FIRST_COMPLETED wins)
DEFAULT_PROVIDERS = ["deepseek", "gemini_flash", "deepseek_flash", "gemini_pro", "groq", "glm_flash"]
MAX_ATTEMPTS = 6  # v10: 全量并行竞速（不再限制4个），最快 provider 返回即取消其余
_LLM_CALL_TIMEOUT = 5.0  # per-provider timeout (balanced: fast enough, reliable enough)

# ── In-memory fallback cache (always available) ──
_cache: dict[str, tuple[float, str, str]] = {}
_CACHE_TTL = 300


def _cache_key(*parts: str) -> str:
    """Generate cache key from one or more strings."""
    return hashlib.sha256("|||".join(parts).encode()).hexdigest()


# ── Token estimation ──
# v10: 优先使用 tiktoken 精确计数（cl100k_base 兼容 DeepSeek/GPT-4o/GLM/ERNIE 等主流模型），
# 不可用时回退到启发式估算。

_tiktoken_enc = None
_tiktoken_available = False


def _get_encoder():
    """Lazy-load tiktoken encoder with graceful fallback."""
    global _tiktoken_enc, _tiktoken_available
    if _tiktoken_enc is not None:
        return _tiktoken_enc
    try:
        import tiktoken
        _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        _tiktoken_available = True
        return _tiktoken_enc
    except (ImportError, Exception):
        _tiktoken_available = False
        return None


def estimate_tokens(text: str) -> int:
    """精确 token 计数（tiktoken cl100k_base），不可用时回退启发式。

    cl100k_base 适用范围：GPT-4, GPT-3.5-turbo, DeepSeek V3/R1, text-embedding-3-*
    """
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # 启发式回退
    chinese = sum(1 for c in text if '一' <= c <= '鿿')
    other = max(len(text) - chinese, 0)
    return int(chinese * 0.6 + other * 0.25)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """精确估算 messages 数组总 token 数。

    包含 content + role 开销（每条消息约 4 token）。
    """
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content", "")) + 4
    return total


def is_tiktoken_available() -> bool:
    """检查 tiktoken 是否可用（用于日志/调试）。"""
    _get_encoder()
    return _tiktoken_available


async def llm_call(
    *,
    system_prompt: str,
    user_message: str,
    messages: list[dict] | None = None,  # v10: 完整 messages 数组（含多轮历史），优先于 system_prompt+user_message
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
        system_prompt: System prompt (used only if messages is None)
        user_message: User message (used only if messages is None)
        messages: Full messages array including system+history+user. When provided,
                  system_prompt and user_message are IGNORED.
        providers: Ordered list of provider keys to try. Defaults to DEFAULT_PROVIDERS.
        per_provider_timeout: Timeout per provider in seconds. Defaults to _LLM_CALL_TIMEOUT.

    Returns:
        (content, provider_name, elapsed_ms)
    """
    # ── Build messages array (支持两种调用模式) ──
    if messages is not None:
        # v10: 使用完整 messages 数组（含多轮历史）
        final_messages = messages
        cache_key_text = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    else:
        # 兼容旧调用方式
        final_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        cache_key_text = f"{system_prompt}|||{user_message}"

    ck = _cache_key(cache_key_text[:500], cache_key_text[:500])

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
        except Exception as e:
            append_log("DEBUG", f"{node_name} Redis缓存读取失败: {type(e).__name__}")

    # ── 2. In-memory cache check ──
    if not bypass_cache and ck in _cache:
        expiry, content, provider = _cache[ck]
        if time.time() < expiry:
            append_log("INFO", f"{node_name} 命中内存缓存 (provider={provider})")
            if stream_callback:
                await stream_callback(content)
            return content, provider, 0.0
        del _cache[ck]

    # Token estimate for logging
    est_tokens = estimate_messages_tokens(final_messages)

    # ── 3. Determine providers ──
    provider_list = list(providers or DEFAULT_PROVIDERS)
    if not provider_list:
        provider_list = list(DEFAULT_PROVIDERS)
    provider_list = provider_list[:MAX_ATTEMPTS]
    timeout = per_provider_timeout or _LLM_CALL_TIMEOUT

    async def _try_provider(provider: str) -> tuple[str, str] | None:
        # ── Circuit breaker check ──
        from app.core.circuit_breaker import get_breaker
        breaker = get_breaker(provider)
        if not breaker.allow_request():
            return None  # 熔断中，静默跳过

        try:
            client = get_llm_client(provider)
            model = get_model_name(provider)

            kwargs: dict = {
                "model": model,
                "messages": final_messages,
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
            breaker.on_success()  # 报告成功 → 重置熔断计数

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
            except Exception as e:
                append_log("DEBUG", f"{node_name} Redis缓存写入失败: {type(e).__name__}")

            return content, provider
        except (asyncio.TimeoutError, Exception) as e:
            breaker.on_failure(str(e)[:100])  # 报告失败 → 累加熔断计数
            return None

    t_total = time.perf_counter()

    # ── 4. v10: True Parallel Race ──
    # 所有 provider 同时启动，谁先返回有效结果就用谁，其余立即取消。
    # 单个 provider 超时 = per_provider_timeout (默认5s)，不阻塞其他。
    tasks = [asyncio.create_task(_try_provider(p)) for p in provider_list]
    racing_timeout = timeout * 2  # 总超时 = 2×单provider超时（给足并行竞争时间）

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
            timeout=racing_timeout,
        )
        for t in done:
            result = t.result()
            if result is not None:
                for pt in pending:
                    pt.cancel()
                content, provider = result
                elapsed_ms = (time.perf_counter() - t_total) * 1000
                append_log(
                    "SUCCESS",
                    f"{node_name} 竞速完成 ({elapsed_ms:.0f}ms, est_tokens={est_tokens}) "
                    f"winner={provider} raced={len(provider_list)}providers",
                )
                return content, provider, elapsed_ms

        # 还没有结果 → 继续等 remaining pending
        if pending:
            done2, pending2 = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=racing_timeout,
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
    append_log("WARN", f"{node_name} 全部竞速失败 ({elapsed_ms:.0f}ms, {len(provider_list)} providers)")
    return "", "", elapsed_ms


# ═══════════════════════════════════════════════════════════════════════
# Function Calling — 结构化工具调用
# ═══════════════════════════════════════════════════════════════════════

async def llm_call_with_tools(
    *,
    system_prompt: str,
    user_message: str,
    messages: list[dict] | None = None,  # v10: 完整 messages 数组（优先）
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
        system_prompt: 系统提示（仅在 messages=None 时使用）
        user_message: 用户消息（仅在 messages=None 时使用）
        messages: 完整 messages 数组（优先于 system_prompt+user_message）
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
    # ── Build messages array ──
    if messages is not None:
        final_messages = messages
    else:
        final_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    provider_list = list(providers or DEFAULT_PROVIDERS)
    if not provider_list:
        provider_list = list(DEFAULT_PROVIDERS)
    provider_list = provider_list[:MAX_ATTEMPTS]
    timeout = per_provider_timeout or _LLM_CALL_TIMEOUT

    est_tokens = estimate_messages_tokens(final_messages)

    async def _try_provider(provider: str) -> tuple[list[dict], str] | None:
        from app.core.circuit_breaker import get_breaker
        breaker = get_breaker(provider)
        if not breaker.allow_request():
            return None
        try:
            client = get_llm_client(provider)
            model = get_model_name(provider)

            kwargs: dict = {
                "model": model,
                "messages": final_messages,
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
            breaker.on_success()
            return [], provider

        except (asyncio.TimeoutError, Exception) as e:
            breaker.on_failure(str(e)[:100])
            return None

    t_total = time.perf_counter()

    # v10: True Parallel Race (same simplified pattern as llm_call)
    tasks = [asyncio.create_task(_try_provider(p)) for p in provider_list]
    racing_timeout = timeout * 2

    try:
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED, timeout=racing_timeout,
        )
        for t in done:
            result = t.result()
            if result is not None:
                for pt in pending:
                    pt.cancel()
                tool_calls, provider = result
                elapsed_ms = (time.perf_counter() - t_total) * 1000
                return tool_calls, provider, elapsed_ms

        if pending:
            done2, pending2 = await asyncio.wait(
                pending, return_when=asyncio.FIRST_COMPLETED, timeout=racing_timeout,
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
    append_log("WARN", f"{node_name} tool_call 竞速全部失败 ({elapsed_ms:.0f}ms)")
    return [], "", elapsed_ms
