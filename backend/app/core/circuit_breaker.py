"""Circuit Breaker — 模型熔断保护。

当某个 LLM provider 连续失败达到阈值时，自动将其熔断（跳过），
避免在故障模型上浪费时间和资源。熔断状态下定期探测恢复。

状态机: CLOSED → (fail_count > threshold) → OPEN → (timeout) → HALF_OPEN → (success) → CLOSED
"""

import time
import threading
from enum import Enum
from dataclasses import dataclass, field
from app.api.v1.admin import append_log


class CircuitState(str, Enum):
    CLOSED = "closed"       # 正常 — 请求通过
    OPEN = "open"           # 熔断 — 拒绝所有请求
    HALF_OPEN = "half_open"  # 半开 — 允许探测请求


@dataclass
class CircuitConfig:
    """熔断器配置"""
    failure_threshold: int = 3       # 连续失败 N 次后熔断
    success_threshold: int = 1       # 半开状态下连续成功 N 次后关闭
    timeout_seconds: float = 30.0    # 熔断持续时间（OPEN → HALF_OPEN）
    half_open_max_requests: int = 1  # 半开状态下允许的最大请求数


@dataclass
class _CircuitState:
    state: CircuitState = CircuitState.CLOSED
    fail_count: int = 0
    success_count: int = 0
    last_fail_time: float = 0.0
    opened_at: float = 0.0
    half_open_requests: int = 0


class CircuitBreaker:
    """LLM Provider 熔断器。

    用法:
        breaker = CircuitBreaker("deepseek", CircuitConfig(failure_threshold=3))

        async with breaker:
            if breaker.allow_request():
                result = await call_llm()
                breaker.on_success()
            else:
                # 熔断中，跳过
                pass
    """

    def __init__(self, name: str, config: CircuitConfig | None = None):
        self.name = name
        self.config = config or CircuitConfig()
        self._state = _CircuitState()
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        """检查是否允许请求通过。"""
        with self._lock:
            now = time.time()

            if self._state.state == CircuitState.CLOSED:
                return True

            if self._state.state == CircuitState.OPEN:
                if now - self._state.opened_at > self.config.timeout_seconds:
                    # 熔断超时 → 半开
                    self._state.state = CircuitState.HALF_OPEN
                    self._state.half_open_requests = 0
                    self._state.success_count = 0
                    append_log(
                        "INFO",
                        f"熔断器 [{self.name}]: OPEN → HALF_OPEN (探测恢复)",
                    )
                    return True
                return False

            if self._state.state == CircuitState.HALF_OPEN:
                if self._state.half_open_requests < self.config.half_open_max_requests:
                    self._state.half_open_requests += 1
                    return True
                return False

            return True

    def on_success(self):
        """请求成功回调。"""
        with self._lock:
            self._state.fail_count = 0
            if self._state.state == CircuitState.HALF_OPEN:
                self._state.success_count += 1
                if self._state.success_count >= self.config.success_threshold:
                    self._state.state = CircuitState.CLOSED
                    append_log(
                        "SUCCESS",
                        f"熔断器 [{self.name}]: HALF_OPEN → CLOSED (已恢复)",
                    )

    def on_failure(self, error: str = ""):
        """请求失败回调。"""
        with self._lock:
            self._state.fail_count += 1
            self._state.last_fail_time = time.time()

            if self._state.state == CircuitState.CLOSED:
                if self._state.fail_count >= self.config.failure_threshold:
                    self._state.state = CircuitState.OPEN
                    self._state.opened_at = time.time()
                    append_log(
                        "WARN",
                        f"熔断器 [{self.name}]: CLOSED → OPEN "
                        f"(连续{self._state.fail_count}次失败: {error[:80]})",
                    )
            elif self._state.state == CircuitState.HALF_OPEN:
                # 半开状态下失败 → 重新熔断
                self._state.state = CircuitState.OPEN
                self._state.opened_at = time.time()
                append_log(
                    "WARN",
                    f"熔断器 [{self.name}]: HALF_OPEN → OPEN "
                        f"(探测失败: {error[:80]})",
                )

    @property
    def state(self) -> CircuitState:
        return self._state.state

    @property
    def is_open(self) -> bool:
        return self._state.state == CircuitState.OPEN

    def reset(self):
        """手动重置熔断器。"""
        with self._lock:
            self._state = _CircuitState()
            append_log("INFO", f"熔断器 [{self.name}]: 手动重置 → CLOSED")


# ═══════════════════════════════════════════════════════════════════════
# 全局熔断器注册表 — 每个 provider 一个实例
# ═══════════════════════════════════════════════════════════════════════

_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(provider: str) -> CircuitBreaker:
    """获取指定 provider 的熔断器（单例）。"""
    with _breakers_lock:
        if provider not in _breakers:
            _breakers[provider] = CircuitBreaker(provider)
        return _breakers[provider]


def get_breaker_states() -> dict[str, dict]:
    """获取所有熔断器状态（用于 /admin 监控）。"""
    return {
        name: {
            "state": b.state.value,
            "fail_count": b._state.fail_count,
            "is_open": b.is_open,
        }
        for name, b in _breakers.items()
    }


def reset_all_breakers():
    """重置所有熔断器"""
    for b in _breakers.values():
        b.reset()
