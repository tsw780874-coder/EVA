"""Performance timing utilities.

Usage:
    from app.core.perf import TimedOperation, get_timer

    timer = get_timer()
    timer.start("pipeline")

    async with TimedOperation("llm_call", timer):
        result = await llm_call(...)

    timer.start("compute")
    price = compute_price_analysis(...)
    timer.stop("compute")

    breakdown = timer.report()
    # → {"llm_call_ms": 823, "compute_ms": 2, "pipeline_ms": 825}
"""

import time
import json
from contextlib import asynccontextmanager


class PerfTimer:
    """Collects named timing measurements."""

    def __init__(self):
        self._starts: dict[str, float] = {}
        self._elapsed: dict[str, float] = {}

    def start(self, label: str):
        self._starts[label] = time.perf_counter()

    def stop(self, label: str) -> float:
        if label not in self._starts:
            return 0.0
        elapsed = (time.perf_counter() - self._starts[label]) * 1000
        self._elapsed[label] = elapsed
        del self._starts[label]
        return elapsed

    def elapsed_ms(self, label: str) -> float:
        """Get elapsed time without stopping the timer."""
        if label in self._starts:
            return (time.perf_counter() - self._starts[label]) * 1000
        return self._elapsed.get(label, 0.0)

    def record(self, label: str, elapsed_ms: float):
        """Manually record a timing."""
        self._elapsed[label] = elapsed_ms

    def report(self) -> dict[str, float]:
        """Return timing breakdown as a dict."""
        result = {}
        for label, elapsed in sorted(self._elapsed.items()):
            result[f"{label}_ms"] = round(elapsed, 1)
        return result

    def report_str(self) -> str:
        """Human-readable timing breakdown."""
        parts = []
        for label, elapsed in sorted(self._elapsed.items()):
            parts.append(f"{label}: {elapsed:.0f}ms")
        return " | ".join(parts)

    def report_json(self) -> str:
        return json.dumps(self.report(), ensure_ascii=False)


class TimedOperation:
    """Async context manager for timing a block of code."""

    def __init__(self, label: str, timer: PerfTimer | None = None):
        self.label = label
        self._timer = timer
        self._own_timer = timer is None
        self._elapsed = 0.0

    async def __aenter__(self):
        if self._own_timer:
            self._timer = PerfTimer()
        self._timer.start(self.label)
        return self

    async def __aexit__(self, *args):
        self._elapsed = self._timer.stop(self.label)

    @property
    def elapsed_ms(self) -> float:
        return self._elapsed


# Global timer for the current request cycle
# Note: PerfTimer is NOT thread/async-safe — keep it per-request
def get_timer() -> PerfTimer:
    return PerfTimer()
