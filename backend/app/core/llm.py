"""Unified LLM client supporting 7 AI models with tier-based access.

v2 optimisations:
- Shared httpx.AsyncClient with connection pooling (HTTP keep-alive)
  so repeated calls don't pay TCP/TLS handshake cost.
- Per-provider AsyncOpenAI client cache — created once and reused.
"""
import asyncio
import time
import httpx
from openai import AsyncOpenAI
from app.config import get_settings

_CLIENT_TIMEOUT = httpx.Timeout(connect=3.0, read=8.0, write=5.0, pool=3.0)

# Shared transport with connection pooling — created once, reused across providers
_shared_http_client = httpx.AsyncClient(
    timeout=_CLIENT_TIMEOUT,
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
)

# Per-provider AsyncOpenAI client cache
_client_cache: dict[str, AsyncOpenAI] = {}

# === 模型层级定义 ===
# admin: 全部可用
# user (free): glm_flash, glm47_flash, ernie_speed, ernie35, seedream

MODEL_TIERS: dict[str, dict] = {
    "deepseek": {
        "tier": "admin",
        "label": "DeepSeek V4 Pro",
        "provider": "DeepSeek",
        "desc": "管理员主力模型，最强推理能力",
    },
    "openai": {
        "tier": "admin",
        "label": "GPT-4o",
        "provider": "OpenAI",
        "desc": "高精度旗舰，多模态识别",
    },
    "glm_flash": {
        "tier": "free",
        "label": "GLM-4-Flash",
        "provider": "智谱AI",
        "desc": "免费快速推理，日常购物助手",
    },
    "glm47_flash": {
        "tier": "free",
        "label": "GLM-4.7-Flash",
        "provider": "智谱AI",
        "desc": "最新快速推理，性能更强",
    },
    "ernie_speed": {
        "tier": "free",
        "label": "ERNIE-Speed-8K",
        "provider": "百度",
        "desc": "轻量快速响应，低延迟体验",
    },
    "ernie35": {
        "tier": "free",
        "label": "ERNIE-3.5-8K",
        "provider": "百度",
        "desc": "标准模型，稳定可靠",
    },
    "seedream": {
        "tier": "free",
        "label": "Seedream",
        "provider": "火山引擎",
        "desc": "图像生成与视觉分析",
    },
    "groq": {
        "tier": "free",
        "label": "Groq LPU",
        "provider": "Groq",
        "desc": "极速推理，500+ tokens/s，最低延迟",
    },
}

# === 配额体系（按 tier 分级）===
TIER_QUOTA: dict[str, int] = {
    "admin": 500000,
    "free": 100000,
}

# === token 用量追踪（按用户隔离）===
# { user_id: { provider_key: used_count } }
_token_usage: dict[str, dict[str, int]] = {}
_MAX_TOKEN_USAGE_ENTRIES = 10_000  # Evict oldest entries when exceeding this limit

# === 实测延迟追踪（按 provider_key 存储最近一次测量值）===
_model_latency: dict[str, float] = {}

# === 验证缓存 ===
_verified_models: dict[str, bool] = {}


def get_llm_client(provider: str | None = None) -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client sharing a pooled HTTP transport."""
    key = provider or "__default__"
    if key in _client_cache:
        return _client_cache[key]

    settings = get_settings()

    configs = {
        "deepseek": (settings.deepseek_api_key, settings.deepseek_base_url),
        "openai": (settings.openai_api_key, settings.openai_base_url),
        "glm_flash": (getattr(settings, "glm_flash_api_key", ""), getattr(settings, "glm_flash_base_url", "https://open.bigmodel.cn/api/paas/v4")),
        "glm47_flash": (getattr(settings, "glm47_flash_api_key", ""), getattr(settings, "glm47_flash_base_url", "https://open.bigmodel.cn/api/paas/v4")),
        "ernie_speed": (getattr(settings, "ernie_speed_api_key", ""), getattr(settings, "ernie_speed_base_url", "https://qianfan.baidubce.com/v2")),
        "ernie35": (getattr(settings, "ernie35_api_key", ""), getattr(settings, "ernie35_base_url", "https://qianfan.baidubce.com/v2")),
        "seedream": (getattr(settings, "seedream_api_key", ""), "https://ark.cn-beijing.volces.com/api/v3"),
        "groq": (getattr(settings, "groq_api_key", ""), getattr(settings, "groq_base_url", "https://api.groq.com/openai/v1")),
    }

    if provider and provider in configs:
        api_key, base_url = configs[provider]
        client = AsyncOpenAI(
            api_key=api_key, base_url=base_url,
            timeout=_CLIENT_TIMEOUT, http_client=_shared_http_client,
        )
    else:
        cfg = settings.llm_config
        client = AsyncOpenAI(
            api_key=cfg["api_key"], base_url=cfg["base_url"],
            timeout=_CLIENT_TIMEOUT, http_client=_shared_http_client,
        )

    _client_cache[key] = client
    return client


def get_model_name(provider: str | None = None) -> str:
    settings = get_settings()
    model_map = {
        "deepseek": settings.deepseek_model,
        "openai": settings.openai_model,
        "glm_flash": getattr(settings, "glm_flash_model", "glm-4-flash"),
        "glm47_flash": getattr(settings, "glm47_flash_model", "glm-4.7-flash"),
        "ernie_speed": getattr(settings, "ernie_speed_model", "ernie-speed-8k"),
        "ernie35": getattr(settings, "ernie35_model", "ernie-3.5-8k"),
        "seedream": "seedream-v3",
        "groq": getattr(settings, "groq_model", "llama-3.1-8b-instant"),
    }
    if provider and provider in model_map:
        return model_map[provider]
    cfg = settings.llm_config
    return cfg["model"]


def get_models_for_role(role: str) -> list[dict]:
    """根据用户角色返回可用模型列表"""
    all_models = get_available_models()
    if role == "admin":
        return all_models
    return [m for m in all_models if m["tier"] == "free"]


def get_available_models(user_id: str | None = None) -> list[dict]:
    """返回所有已配置的模型列表及实测状态（按用户维度 token 隔离）"""
    settings = get_settings()
    models = []

    key_map = {
        "deepseek": "deepseek_api_key",
        "openai": "openai_api_key",
        "glm_flash": "glm_flash_api_key",
        "glm47_flash": "glm47_flash_api_key",
        "ernie_speed": "ernie_speed_api_key",
        "ernie35": "ernie35_api_key",
        "seedream": "seedream_api_key",
        "groq": "groq_api_key",
    }
    for key, info in MODEL_TIERS.items():
        api_key = getattr(settings, key_map.get(key, ""), "")
        if not api_key:
            continue

        is_verified = _verified_models.get(key, None)
        if is_verified is True:
            status = "available"
        elif is_verified is False:
            status = "unavailable"
        else:
            status = "unverified"

        # 用户维度的 token 用量（真实追踪数据）
        used = 0
        if user_id and user_id in _token_usage:
            used = _token_usage[user_id].get(key, 0)

        # 配额按 tier 分级
        tier = info["tier"]
        total_quota = TIER_QUOTA.get(tier, 100000)
        remaining = max(total_quota - used, 0)

        # 实测延迟（来自 verify_model 或实际调用测量）
        measured_latency = _model_latency.get(key, None)

        models.append({
            "name": info["label"],
            "provider": info["provider"],
            "desc": info["desc"],
            "status": status,
            "tier": tier,
            "key": key,
            "total_quota": total_quota,
            "used_tokens": used,
            "remaining_tokens": remaining,
            "latency_ms": round(measured_latency) if measured_latency else None,
        })

    return models


def track_token_usage(user_id: str, provider_key: str, token_count: int):
    """追踪用户维度的 token 用量（用户间隔离），带自动淘汰防止内存泄漏。"""
    if not user_id:
        return
    if user_id not in _token_usage:
        # Evict oldest entries when dict grows too large
        if len(_token_usage) >= _MAX_TOKEN_USAGE_ENTRIES:
            # Remove 20% oldest entries (dict preserves insertion order in Python 3.7+)
            to_remove = int(_MAX_TOKEN_USAGE_ENTRIES * 0.2)
            keys = list(_token_usage.keys())[:to_remove]
            for k in keys:
                del _token_usage[k]
        _token_usage[user_id] = {}
    if provider_key not in _token_usage[user_id]:
        _token_usage[user_id][provider_key] = 0
    _token_usage[user_id][provider_key] += token_count


def track_model_latency(provider_key: str, latency_ms: float):
    """记录模型实测延迟"""
    if latency_ms > 0:
        # 指数移动平均，平滑波动
        if provider_key in _model_latency:
            _model_latency[provider_key] = _model_latency[provider_key] * 0.7 + latency_ms * 0.3
        else:
            _model_latency[provider_key] = latency_ms


def get_user_token_usage(user_id: str, provider_key: str | None = None) -> int:
    """获取用户 token 用量"""
    user_usage = _token_usage.get(user_id, {})
    if provider_key:
        return user_usage.get(provider_key, 0)
    return sum(user_usage.values())


async def verify_model(provider_key: str) -> bool:
    """验证单个模型是否可用，同时测量延迟"""
    settings = get_settings()
    key_map = {
        "deepseek": "deepseek_api_key",
        "openai": "openai_api_key",
        "glm_flash": "glm_flash_api_key",
        "glm47_flash": "glm47_flash_api_key",
        "ernie_speed": "ernie_speed_api_key",
        "ernie35": "ernie35_api_key",
        "seedream": "seedream_api_key",
        "groq": "groq_api_key",
    }
    api_key = getattr(settings, key_map.get(provider_key, ""), "")
    if not api_key:
        _verified_models[provider_key] = False
        return False

    try:
        client = get_llm_client(provider_key)
        model = get_model_name(provider_key)

        t0 = time.perf_counter()
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            ),
            timeout=20,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        track_model_latency(provider_key, elapsed_ms)

        ok = resp.choices is not None and len(resp.choices) > 0
        _verified_models[provider_key] = ok
        return ok
    except Exception:
        _verified_models[provider_key] = False
        return False


async def verify_all_models() -> dict[str, bool]:
    """验证所有模型（并行执行，7 个模型同时验证）"""
    keys = list(MODEL_TIERS)
    results_list = await asyncio.gather(*(verify_model(k) for k in keys))
    return dict(zip(keys, results_list))


def get_model_config(provider_key: str) -> dict:
    """获取特定 provider 的 LLM 配置"""
    settings = get_settings()
    return {
        "api_key": get_llm_client(provider_key).api_key,
        "base_url": str(get_llm_client(provider_key).base_url),
        "model": get_model_name(provider_key),
    }
