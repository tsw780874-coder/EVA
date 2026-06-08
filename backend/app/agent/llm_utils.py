"""LLM call utility — race-based with streaming callback.

Single-purpose module.  No token queues, no graph coupling.
Callers pass an optional async callback for streaming tokens.
"""

import asyncio
import hashlib
import time
from typing import Callable, Awaitable
from app.core.llm import get_llm_client, get_model_name, track_token_usage, track_model_latency
from app.api.v1.admin import append_log

FALLBACK_ORDER = ["groq", "glm_flash", "ernie35", "deepseek", "openai", "glm47_flash", "ernie_speed"]
MAX_ATTEMPTS = 4
_LLM_CALL_TIMEOUT = 2.5  # per-provider timeout — Groq LPU responds in < 500ms

# Response cache: key → (expiry_ts, content, provider)
_cache: dict[str, tuple[float, str, str]] = {}
_CACHE_TTL = 300


def _cache_key(system_prompt: str, user_message: str) -> str:
    return hashlib.sha256(f"{system_prompt}|||{user_message}".encode()).hexdigest()


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
) -> tuple[str, str]:
    """Race multiple providers, return first successful response.

    When stream_callback is provided, it's called for each token chunk
    as it arrives — the caller gets progressive output before this
    function returns.
    """
    ck = _cache_key(system_prompt, user_message)

    if not bypass_cache and ck in _cache:
        expiry, content, provider = _cache[ck]
        if time.time() < expiry:
            append_log("INFO", f"{node_name} 命中缓存 (provider={provider})")
            if stream_callback:
                await stream_callback(content)
            return content, provider
        del _cache[ck]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

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
                    timeout=_LLM_CALL_TIMEOUT,
                )
                chunks: list[str] = []
                async for chunk in resp:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        chunks.append(delta.content)
                        await stream_callback(delta.content)
                content = "".join(chunks)
            else:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(**kwargs),
                    timeout=_LLM_CALL_TIMEOUT,
                )
                content = resp.choices[0].message.content or ""
                if resp.usage:
                    track_token_usage(user_id, provider, resp.usage.total_tokens)

            elapsed_ms = (time.perf_counter() - t0) * 1000
            track_model_latency(provider, elapsed_ms)

            _cache[ck] = (time.time() + _CACHE_TTL, content, provider)
            return content, provider
        except (asyncio.TimeoutError, Exception):
            return None

    providers = FALLBACK_ORDER[:MAX_ATTEMPTS]
    tasks = [asyncio.create_task(_try_provider(p)) for p in providers]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            result = t.result()
            if result is not None:
                for pt in pending:
                    pt.cancel()
                return result

        # Second wave
        if pending:
            done2, pending2 = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=2.0)
            for t in done2:
                result = t.result()
                if result is not None:
                    for pt in pending2:
                        pt.cancel()
                    return result
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    append_log("WARN", f"{node_name} 模型调用全部失败")
    return "", ""
